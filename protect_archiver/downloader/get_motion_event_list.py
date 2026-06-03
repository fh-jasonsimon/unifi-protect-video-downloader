# get motion events list
import logging

from datetime import datetime
from typing import Any
from typing import Counter
from typing import Dict
from typing import List

import requests

from protect_archiver.dataclasses import Camera
from protect_archiver.dataclasses import MotionEvent


def get_detection_list(
    session: Any, start: datetime, end: datetime, camera_list: List[Camera]
) -> List[Dict[str, Any]]:
    """Fetch the raw detection (event) payloads from the Protect /events API.

    Returns the list of raw event dicts exactly as returned by the API (ongoing
    events without an 'end' are filtered out). Returns an empty list on a non-200
    response. Network-level errors propagate to the caller so they can be handled
    (e.g. retried or skipped) per request.
    """
    motion_events_uri = (
        # TODO: REMARK 2024-Jan-29 @danielfernau #388
        # TODO: The API has been updated and now uses 'type' multiple times instead of a list.
        # TODO: The query parameters documented below are mostly still correct but need to be checked.
        # TODO: Param "withoutDescriptions=true" should be present to avoid unnecessary data in the response.
        f"{session.authority}{session.base_path}/events?"
        "type=motion&type=smartDetectZone&type=smartDetectLine&type=smartAudioDetect&type=ring&"
        "type=doorAccess&smartDetectType=licensePlate&withoutDescriptions=true"
        f"&start={int(start.timestamp()) * 1000}&end={int(end.timestamp()) * 1000}"
        f"&start={int(start.timestamp()) * 1000}&end={int(end.timestamp()) * 1000}"
    )

    response = (
        requests.get(
            motion_events_uri,
            cookies={"TOKEN": session.get_api_token()},
            verify=session.verify_ssl,
        )
        if session.__class__.__name__ == "UniFiOSClient"
        else requests.get(
            motion_events_uri,
            headers={"Authorization": f"Bearer {session.get_api_token()}"},
            verify=session.verify_ssl,
        )
    )

    if response.status_code != 200:
        print(f"Error while loading motion events list: {response.status_code}")
        return []

    logging.info(f"Successfully retrieved data from {motion_events_uri}")
    # filter ongoing event with no end date https://github.com/danielfernau/unifi-protect-video-downloader/issues/65
    detections = [detection for detection in response.json() if detection.get("end")]

    # noinspection PyTypeHints
    event_count_by_camera = Counter(d["camera"] for d in detections)
    if event_count_by_camera:
        logging.info(
            "Events found:\n{}".format(
                "\n".join(
                    f"{event_count_by_camera[x]} motion"
                    f" event{'s' if event_count_by_camera[x] > 1 else ''} found for camera"
                    f" '{next((c.name for c in camera_list if c.id == x), x)}' ({x}) between"
                    f" {start} and {end}"
                    for x in event_count_by_camera
                )
            )
        )

    logging.info(
        f"{len(detections)} motion events found for all selected cameras between {start} and {end}"
    )

    return detections


def get_motion_event_list(
    session: Any, start: datetime, end: datetime, camera_list: List[Camera]
) -> List[MotionEvent]:
    return [
        MotionEvent(
            id=detection["id"],
            start=datetime.fromtimestamp(detection["start"] / 1000),
            end=datetime.fromtimestamp(detection["end"] / 1000),
            camera_id=detection["camera"],
            score=detection["score"],
            thumbnail_id=detection["thumbnail"],
            heatmap_id=detection["heatmap"],
        )
        for detection in get_detection_list(session, start, end, camera_list)
    ]

import json
import logging
import os
import time

from datetime import datetime
from typing import Any
from typing import Dict
from typing import List

from protect_archiver.dataclasses import Camera
from protect_archiver.downloader.get_motion_event_list import get_detection_list
from protect_archiver.downloader.upload_to_s3 import upload_to_s3
from protect_archiver.utils import build_download_dir
from protect_archiver.utils import calculate_day_intervals
from protect_archiver.utils import make_camera_name_fs_safe


# Download detection (event) metadata as JSON instead of footage.
#
# For every camera in camera_list, all raw detection payloads in [start, end) are
# written batched one JSON file per camera per day into the same
# 'YYYY/MM/DD/<camera_name>/' structure used for footage, so a downstream process can
# join detections to the already-downloaded video chunks by camera + timestamp range.
#
# The /events API is queried one calendar day at a time so that very large ranges do
# not ride on a single huge request, and every day-fetch and per-camera write is
# wrapped so that a single failure is logged and counted but never aborts the run.
def download_detections(
    client: Any, start: datetime, end: datetime, camera_list: List[Camera]
) -> None:
    cameras_by_id = {camera.id: camera for camera in camera_list}

    logging.info(
        f"Downloading detection metadata for {len(camera_list)} camera(s) between {start} and {end}"
    )

    for day_anchor, query_start, query_end in calculate_day_intervals(
        start, end, client.use_utc_filenames
    ):
        day_str = day_anchor.strftime("%Y-%m-%d")

        # be gentle on the controller between day requests (if configured)
        if client.download_wait:
            time.sleep(int(client.download_wait))

        # fetch all detections for this day - resilient to per-day failures
        try:
            detections = get_detection_list(client.session, query_start, query_end, camera_list)
        except Exception as e:
            logging.exception(f"Failed to fetch detections for {day_str}: {e}")
            client.files_failed += 1
            continue

        # group detections by camera, keeping only the selected cameras
        detections_by_camera: Dict[str, List[Dict[str, Any]]] = {}
        for detection in detections:
            camera_id = detection.get("camera")
            if camera_id in cameras_by_id:
                detections_by_camera.setdefault(camera_id, []).append(detection)

        # write one JSON file per camera per day - resilient to per-file failures
        for camera_id, camera_detections in detections_by_camera.items():
            camera = cameras_by_id[camera_id]
            try:
                _save_detections(
                    client, camera, day_anchor, day_str, query_start, query_end, camera_detections
                )
            except Exception as e:
                logging.exception(
                    f"Failed to save detections for camera '{camera.name}' on {day_str}: {e}"
                )
                client.files_failed += 1
                continue

        # flush status records for this day as we go (memory-friendly over long ranges)
        if client.status_tracker is not None:
            client.status_tracker.flush_day(day_anchor.strftime("%Y_%m_%d"))


def _save_detections(
    client: Any,
    camera: Camera,
    day_anchor: datetime,
    day_str: str,
    query_start: datetime,
    query_end: datetime,
    detections: List[Dict[str, Any]],
) -> None:
    # make camera name safe for use in file name
    camera_name_fs_safe = make_camera_name_fs_safe(camera)

    download_dir = build_download_dir(
        use_subfolders=client.use_subfolders,
        destination_path=client.destination_path,
        interval_start_tz=day_anchor,
        camera_name_fs_safe=camera_name_fs_safe,
    )

    filename = f"{download_dir}/{camera_name_fs_safe} - {day_str} - detections.json"

    # skip writing files that already exist on disk if --skip-existing-files is present
    if bool(client.skip_existing_files) and os.path.exists(filename):
        logging.info(
            f"File {filename} already exists on disk and argument '--skip-existing-files' "
            "is present - skipping \n"
        )
        client.files_skipped += 1
        return

    with open(filename, "w") as fp:
        json.dump(detections, fp, indent=2, default=str)

    file_size = os.path.getsize(filename)
    client.files_downloaded += 1
    client.bytes_downloaded += file_size
    logging.info(
        f"Saved {len(detections)} detection(s) for camera '{camera.name}' ({camera.id}) to"
        f" {filename}"
    )

    # upload to S3 if configured (mirrors download_footage behavior)
    upload_status = "n/a"
    if client.s3_bucket is not None:
        if file_size > 0:
            upload_status = upload_to_s3(client, filename)
            if upload_status == "uploaded":
                os.remove(filename)
                logging.info(f"Deleted local file {filename} after successful S3 upload")
        else:
            upload_status = "skipped"

    # record status to CSV
    if client.status_tracker is not None:
        client.status_tracker.add_record(
            camera_name=camera.name,
            interval_start=query_start,
            interval_end=query_end,
            filename=os.path.basename(filename),
            download_status="downloaded",
            upload_status=upload_status,
        )

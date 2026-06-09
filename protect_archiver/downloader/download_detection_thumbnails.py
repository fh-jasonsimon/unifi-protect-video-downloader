import logging
import os
import time

from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Dict
from typing import List

from protect_archiver.dataclasses import Camera
from protect_archiver.downloader.download_file import download_file
from protect_archiver.downloader.get_motion_event_list import get_detection_list
from protect_archiver.downloader.upload_to_s3 import upload_to_s3
from protect_archiver.utils import build_download_dir
from protect_archiver.utils import calculate_day_intervals
from protect_archiver.utils import make_camera_name_fs_safe


# Download the thumbnail image for every detection in [start, end) for the given cameras.
#
# Thumbnails are stored next to the footage/detection JSON in the
# 'YYYY/MM/DD/<camera_name>/thumbnails/' structure (their own 'thumbnails' subfolder so
# the per-camera/day directory isn't flooded with flat image files), named by event
# start time + event ID so a downstream process can match each thumbnail to its video
# chunk and to the entry inside that day's detections JSON.
#
# The /events list is fetched one calendar day at a time, and every day-fetch and every
# per-thumbnail download is wrapped so a single failure is logged and counted but never
# aborts the run (these runs can involve millions of thumbnails).
def download_detection_thumbnails(
    client: Any,
    start: datetime,
    end: datetime,
    camera_list: List[Camera],
    max_height: int = 480,
) -> None:
    cameras_by_id = {camera.id: camera for camera in camera_list}

    logging.info(
        f"Downloading detection thumbnails for {len(camera_list)} camera(s) between {start}"
        f" and {end}"
    )

    for _day_anchor, query_start, query_end in calculate_day_intervals(
        start, end, client.use_utc_filenames
    ):
        day_str = query_start.strftime("%Y-%m-%d")

        # fetch all detections for this day - resilient to per-day failures
        try:
            detections = get_detection_list(client.session, query_start, query_end, camera_list)
        except Exception as e:
            logging.exception(f"Failed to fetch detections for {day_str}: {e}")
            client.files_failed += 1
            continue

        for detection in detections:
            camera_id = detection.get("camera")
            thumbnail_id = detection.get("thumbnail")
            # skip detections for unselected cameras or without a thumbnail asset
            if camera_id not in cameras_by_id or not thumbnail_id:
                continue

            camera = cameras_by_id[camera_id]
            try:
                _download_thumbnail(client, camera, detection, thumbnail_id, max_height)
            except Exception as e:
                logging.exception(
                    f"Failed to download thumbnail for detection"
                    f" {detection.get('id', thumbnail_id)}: {e}"
                )
                client.files_failed += 1
                continue

        # flush status records for this day as we go (memory-friendly over long ranges)
        if client.status_tracker is not None:
            client.status_tracker.flush_day(query_start.strftime("%Y_%m_%d"))


def _download_thumbnail(
    client: Any,
    camera: Camera,
    detection: Dict[str, Any],
    thumbnail_id: str,
    max_height: int,
) -> None:
    camera_name_fs_safe = make_camera_name_fs_safe(camera)

    event_start = datetime.fromtimestamp(detection["start"] / 1000)
    event_end = (
        datetime.fromtimestamp(detection["end"] / 1000) if detection.get("end") else event_start
    )

    # support selection between local time zone and UTC for file names / folders
    interval_start_tz = (
        event_start.astimezone(timezone.utc) if client.use_utc_filenames else event_start
    )

    base_dir = build_download_dir(
        use_subfolders=client.use_subfolders,
        destination_path=client.destination_path,
        interval_start_tz=interval_start_tz,
        camera_name_fs_safe=camera_name_fs_safe,
    )

    # keep thumbnails in their own subfolder so the camera/date directory isn't flooded
    download_dir = os.path.join(base_dir, "thumbnails")
    os.makedirs(download_dir, exist_ok=True)

    filename_timestamp = interval_start_tz.strftime("%Y-%m-%d - %H.%M.%S%z")
    event_id = detection.get("id", thumbnail_id)
    filename = f"{download_dir}/{camera_name_fs_safe} - {filename_timestamp} - {event_id} - thumbnail.jpg"

    # throttle requests against the controller if --wait-between-downloads is set
    if client.download_wait:
        time.sleep(int(client.download_wait))

    thumbnail_query = f"/thumbnails/{thumbnail_id}"
    download_status = download_file(client, thumbnail_query, filename)

    # download_file already counts/handles failed, empty and skipped downloads
    if download_status not in ("downloaded", "already_exists"):
        return

    # scale down to max_height while preserving aspect ratio (never upscaling)
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        _resize_to_max_height(filename, max_height)

    # upload to S3 if configured (mirrors download_footage behavior)
    upload_status = "n/a"
    if client.s3_bucket is not None:
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
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
            interval_start=event_start,
            interval_end=event_end,
            filename=os.path.basename(filename),
            download_status=download_status,
            upload_status=upload_status,
        )


def _resize_to_max_height(filename: str, max_height: int) -> None:
    """Resize the image at filename so its height is at most max_height, preserving the
    aspect ratio and never upscaling. Failures are logged but not fatal."""
    try:
        from PIL import Image

        with Image.open(filename) as img:
            if img.height <= max_height:
                return
            # Image.thumbnail preserves aspect ratio and never enlarges; bounding the
            # width by the current width makes height the binding constraint.
            img.thumbnail((img.width, max_height))
            img.save(filename)
    except Exception as e:
        logging.warning(f"Could not resize thumbnail {filename}: {e}")

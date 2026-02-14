import logging
import os

from typing import Any

from botocore.exceptions import ClientError


def upload_to_s3(client: Any, filename: str) -> str:
    """Upload a local file to S3 and return the upload status.

    The S3 key is derived from the file's path relative to the client's
    destination directory, prefixed with the configured S3 prefix.

    Returns:
        "uploaded" on success, "failed" on error.
    """
    relative_path = os.path.relpath(filename, client.destination_path)
    s3_key = f"{client.s3_prefix}/{relative_path}" if client.s3_prefix else relative_path

    try:
        client.s3_client.upload_file(filename, client.s3_bucket, s3_key)
        logging.info(f"Uploaded {filename} to s3://{client.s3_bucket}/{s3_key}")
        client.files_uploaded += 1
        return "uploaded"
    except ClientError as e:
        logging.error(f"Failed to upload {filename} to S3: {e}")
        client.files_upload_failed += 1
        return "failed"

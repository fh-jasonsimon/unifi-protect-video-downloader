from datetime import datetime
from os import path
from typing import Any
from typing import List
from typing import Optional

from protect_archiver.client.legacy import LegacyClient
from protect_archiver.client.unifi_os import UniFiOSClient
from protect_archiver.config import Config
from protect_archiver.downloader import Downloader


class ProtectClient:
    def __init__(
        self,
        address: str = Config.ADDRESS,
        port: int = Config.PORT,
        protocol: str = Config.PROTOCOL,
        username: str = Config.USERNAME,
        password: Optional[str] = Config.PASSWORD,
        verify_ssl: bool = Config.VERIFY_SSL,
        not_unifi_os: bool = False,
        # use_unsafe_cookie_jar: bool = Config.USE_UNSAFE_COOKIE_JAR,
        ignore_failed_downloads: bool = Config.IGNORE_FAILED_DOWNLOADS,
        download_wait: int = Config.DOWNLOAD_WAIT,
        use_subfolders: bool = Config.USE_SUBFOLDERS,
        skip_existing_files: bool = Config.SKIP_EXISTING_FILES,
        destination_path: str = Config.DESTINATION_PATH,
        touch_files: bool = Config.TOUCH_FILES,
        # aka read_timeout - time to wait until a socket read response happens
        download_timeout: float = Config.DOWNLOAD_TIMEOUT,
        use_utc_filenames: bool = Config.USE_UTC_FILENAMES,
        # S3 upload settings
        s3_bucket: Optional[str] = Config.S3_BUCKET,
        s3_prefix: str = Config.S3_PREFIX,
        s3_region: str = Config.S3_REGION,
        s3_aws_access_key_id: Optional[str] = Config.S3_AWS_ACCESS_KEY_ID,
        s3_aws_secret_access_key: Optional[str] = Config.S3_AWS_SECRET_ACCESS_KEY,
        # status CSV settings
        status_csv_dir: Optional[str] = Config.STATUS_CSV_DIR,
    ) -> None:
        self.protocol = protocol
        self.address = address
        self.port = port if port is not None else 7443 if not_unifi_os else 443
        self.not_unifi_os = not_unifi_os
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl

        self.ignore_failed_downloads = ignore_failed_downloads
        self.download_wait = download_wait
        self.download_timeout = download_timeout
        self.use_subfolders = use_subfolders
        self.skip_existing_files = skip_existing_files
        self.touch_files = touch_files
        self.use_utc_filenames = use_utc_filenames

        self.destination_path = path.abspath(destination_path)

        self.files_downloaded = 0
        self.bytes_downloaded = 0
        self.files_skipped = 0
        self.files_failed = 0
        self.max_retries = 3

        # S3 upload
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix.strip("/") if s3_prefix else ""
        self.s3_region = s3_region
        self._s3_aws_access_key_id = s3_aws_access_key_id
        self._s3_aws_secret_access_key = s3_aws_secret_access_key
        self._s3_client: Any = None
        self.files_uploaded = 0
        self.files_upload_failed = 0

        # status CSV
        self.status_tracker: Any = None
        if status_csv_dir is not None:
            from protect_archiver.status import StatusTracker

            self.status_tracker = StatusTracker(status_csv_dir)

        self._access_key = None
        self._api_token = None

        if not_unifi_os:
            self.port = 7443
            self.base_path = "/api"

            assert self.password
            self.session: Any = LegacyClient(
                self.protocol,
                self.address,
                self.port,
                self.username,
                self.password,
                self.verify_ssl,
            )
        else:
            self.port = 443
            assert self.password
            self.session = UniFiOSClient(
                self.protocol,
                self.address,
                self.port,
                self.username,
                self.password,
                self.verify_ssl,
            )

    def get_camera_list(self) -> List[Any]:
        return Downloader.get_camera_list(self.session)

    def get_motion_event_list(
        self, start: datetime, end: datetime, camera_list: List[Any]
    ) -> List[Any]:
        return Downloader.get_motion_event_list(self.session, start, end, camera_list)

    def get_session(self) -> Any:
        return self.session

    @property
    def s3_client(self) -> Any:
        """Lazily initialize and return the boto3 S3 client."""
        if self._s3_client is None:
            import boto3

            kwargs: dict = {"region_name": self.s3_region}
            if self._s3_aws_access_key_id and self._s3_aws_secret_access_key:
                kwargs["aws_access_key_id"] = self._s3_aws_access_key_id
                kwargs["aws_secret_access_key"] = self._s3_aws_secret_access_key
            self._s3_client = boto3.client("s3", **kwargs)
        return self._s3_client


# TODO
# class ProtectError(object):
#     pass

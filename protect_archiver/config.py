from typing import Optional


class Config:
    def __init__(self) -> None:
        pass

    ADDRESS: str = "unifi"
    PORT: int = 443
    PROTOCOL: str = "https"
    USERNAME: str = "ubnt"
    PASSWORD: Optional[str] = None
    VERIFY_SSL: bool = False
    USE_UNSAFE_COOKIE_JAR: bool = False
    DESTINATION_PATH: str = "./"
    USE_SUBFOLDERS: bool = False
    TOUCH_FILES: bool = False
    SKIP_EXISTING_FILES: bool = False
    IGNORE_FAILED_DOWNLOADS: bool = False
    DISABLE_ALIGNMENT: bool = False
    DISABLE_SPLITTING: bool = False
    DOWNLOAD_WAIT: int = 0
    DOWNLOAD_TIMEOUT: float = (
        60.0  # aka read_timeout - time to wait until a socket read response happens
    )
    MAX_RETRIES: int = 3
    USE_UTC_FILENAMES: bool = False

    # S3 upload settings
    S3_BUCKET: Optional[str] = None
    S3_PREFIX: str = ""
    S3_REGION: str = "us-east-1"
    S3_AWS_ACCESS_KEY_ID: Optional[str] = None
    S3_AWS_SECRET_ACCESS_KEY: Optional[str] = None

    # status CSV settings
    STATUS_CSV_DIR: Optional[str] = None

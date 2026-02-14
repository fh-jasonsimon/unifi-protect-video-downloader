import csv
import logging
import os

from datetime import datetime
from typing import Dict
from typing import List
from typing import Optional


class StatusTracker:
    """Tracks download/upload status per file and writes daily CSV reports."""

    FIELDNAMES = [
        "camera",
        "interval_start",
        "interval_end",
        "filename",
        "download_status",
        "upload_status",
    ]

    def __init__(self, csv_dir: str) -> None:
        self.csv_dir = os.path.abspath(csv_dir)
        self._records: Dict[str, List[Dict[str, str]]] = {}

        if not os.path.isdir(self.csv_dir):
            os.makedirs(self.csv_dir, exist_ok=True)
            logging.info(f"Created status CSV directory {self.csv_dir}")

    def add_record(
        self,
        camera_name: str,
        interval_start: datetime,
        interval_end: datetime,
        filename: str,
        download_status: str,
        upload_status: str,
    ) -> None:
        date_str = interval_start.strftime("%Y_%m_%d")
        if date_str not in self._records:
            self._records[date_str] = []

        self._records[date_str].append(
            {
                "camera": camera_name,
                "interval_start": interval_start.strftime("%Y-%m-%d %H:%M:%S"),
                "interval_end": interval_end.strftime("%Y-%m-%d %H:%M:%S"),
                "filename": filename,
                "download_status": download_status,
                "upload_status": upload_status,
            }
        )

    def flush_day(self, date_str: str) -> None:
        """Write buffered records for the given day to a CSV file and clear the buffer."""
        if date_str not in self._records:
            return

        records = self._records.pop(date_str)
        filepath = os.path.join(self.csv_dir, f"{date_str}.csv")
        write_header = not os.path.exists(filepath)

        with open(filepath, "a", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=self.FIELDNAMES)
            if write_header:
                writer.writeheader()
            writer.writerows(records)

        logging.info(f"Wrote {len(records)} status records to {filepath}")

    def flush_all(self) -> None:
        """Flush all buffered records to their respective CSV files."""
        for date_str in list(self._records.keys()):
            self.flush_day(date_str)

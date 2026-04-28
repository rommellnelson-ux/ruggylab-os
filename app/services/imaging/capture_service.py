from pathlib import Path
import datetime as dt
import re
import uuid


class MicroscopeCaptureService:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def reserve_image_path(self, sample_barcode: str) -> str:
        timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d_%H%M%S")
        safe_barcode = re.sub(r"[^A-Za-z0-9_.-]", "_", sample_barcode).strip("._-")
        if not safe_barcode:
            safe_barcode = "sample"
        filename = f"{safe_barcode}_{timestamp}_{str(uuid.uuid4())[:8]}.jpg"
        return (self.storage_dir / filename).as_posix()

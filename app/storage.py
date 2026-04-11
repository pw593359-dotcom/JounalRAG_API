from pathlib import Path
import re
import shutil
from typing import BinaryIO


def save_upload_stream(
    stream: BinaryIO,
    original_filename: str,
    document_id: str,
    upload_dir: Path,
) -> Path:
    filename = sanitize_filename(original_filename) or "document.pdf"
    document_dir = upload_dir / document_id
    document_dir.mkdir(parents=True, exist_ok=True)
    target = document_dir / filename

    with target.open("wb") as output:
        shutil.copyfileobj(stream, output)

    return target


def delete_document_files(document_id: str, upload_dir: Path) -> None:
    document_dir = upload_dir / document_id
    if document_dir.exists() and document_dir.is_dir():
        shutil.rmtree(document_dir)


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


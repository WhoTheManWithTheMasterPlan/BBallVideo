"""
Local filesystem storage for video and clip files.
Stores on TrueNAS at configurable base path with 1TB limit.

TODO: Better file lifecycle management needed:
  - Cleanup old raw videos + highlights when a job is deleted or re-run
  - Cascade delete: deleting a video/job should remove associated files on disk
  - B: drive SMB mount is read-only from laptop — cleanup must happen server-side
  - Consider periodic storage audit / garbage collection for orphaned files
"""

import shutil
from pathlib import Path

from app.core.config import settings


def _base_path() -> Path:
    """Get and ensure the base storage directory exists."""
    path = Path(settings.storage_base_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_storage_usage_bytes() -> int:
    """Calculate total storage usage in bytes."""
    base = _base_path()
    if not base.exists():
        return 0
    return sum(f.stat().st_size for f in base.rglob("*") if f.is_file())


def check_storage_limit(additional_bytes: int = 0) -> bool:
    """Check if adding additional_bytes would exceed the storage limit."""
    current = get_storage_usage_bytes()
    limit = settings.storage_max_gb * 1024 * 1024 * 1024
    return (current + additional_bytes) <= limit


def get_file_path(file_key: str) -> Path:
    """Convert a file key (e.g. 'raw/game-id/video.mp4') to absolute path."""
    return _base_path() / file_key


def save_file(file_key: str, source_path: str):
    """Save a file from a local source path to storage."""
    dest = get_file_path(file_key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, dest)


def save_upload(file_key: str, data: bytes):
    """Save uploaded file data to storage."""
    dest = get_file_path(file_key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def copy_file(file_key: str, local_path: str):
    """Copy a file from storage to a local path (for processing)."""
    source = get_file_path(file_key)
    shutil.copy2(source, local_path)


def delete_file(file_key: str):
    """Delete a file from storage."""
    path = get_file_path(file_key)
    if path.exists():
        path.unlink()


def file_exists(file_key: str) -> bool:
    """Check if a file exists in storage."""
    return get_file_path(file_key).exists()

"""
Remote file transfer between GPU worker (laptop) and TrueNAS storage via SCP.

Used when REMOTE_STORAGE_ENABLED=true — the worker downloads videos from TrueNAS
before processing and uploads clips/thumbnails back after.
"""

import logging
import subprocess
from pathlib import Path, PurePosixPath

from app.core.config import settings

logger = logging.getLogger(__name__)


def _scp_remote_path(file_key: str) -> str:
    """Build the scp remote path string: user@host:/path/to/file"""
    # Force forward slashes — file_key may contain backslashes on Windows
    remote = f"{settings.remote_storage_path}/{file_key.replace(chr(92), '/')}"
    return f"{settings.remote_storage_user}@{settings.remote_storage_host}:{remote}"


def download_file(file_key: str, local_path: str) -> None:
    """Download a file from TrueNAS to a local path via SCP."""
    local = Path(local_path)
    local.parent.mkdir(parents=True, exist_ok=True)

    remote = _scp_remote_path(file_key)
    logger.info(f"Downloading {file_key} → {local_path}")

    result = subprocess.run(
        ["scp", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", remote, str(local)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"SCP download failed: {result.stderr.strip()}")

    logger.info(f"Downloaded {file_key} ({local.stat().st_size / 1024 / 1024:.1f} MB)")


def upload_file(local_path: str, file_key: str) -> None:
    """Upload a local file to TrueNAS storage via SCP."""
    local = Path(local_path)
    if not local.exists():
        raise FileNotFoundError(f"Local file not found: {local_path}")

    # Ensure remote directory exists (use PurePosixPath — remote is Linux)
    remote_dir = f"{settings.remote_storage_path}/{PurePosixPath(file_key).parent}"
    ssh_target = f"{settings.remote_storage_user}@{settings.remote_storage_host}"
    mkdir_result = subprocess.run(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes",
         ssh_target, f"mkdir -p {remote_dir}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if mkdir_result.returncode != 0:
        logger.warning(f"Failed to create remote dir {remote_dir}: {mkdir_result.stderr.strip()}")
        raise RuntimeError(f"SSH mkdir failed for {remote_dir}: {mkdir_result.stderr.strip()}")

    remote = _scp_remote_path(file_key)
    logger.info(f"Uploading {local_path} → {file_key}")

    result = subprocess.run(
        ["scp", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", str(local), remote],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"SCP upload failed: {result.stderr.strip()}")

    logger.info(f"Uploaded {file_key} ({local.stat().st_size / 1024 / 1024:.1f} MB)")

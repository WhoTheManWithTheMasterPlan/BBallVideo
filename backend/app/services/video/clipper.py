"""
FFmpeg-based video clip extraction.
"""

import subprocess
from pathlib import Path


def extract_clip(
    video_path: str,
    output_path: str,
    start_time: float,
    end_time: float,
    padding: float = 2.0,
) -> str:
    """
    Extract a clip from a video using FFmpeg.

    Args:
        video_path: Path to source video
        output_path: Path for output clip
        start_time: Start time in seconds
        end_time: End time in seconds
        padding: Extra seconds before/after the event
    """
    start = max(0, start_time - padding)
    duration = (end_time - start_time) + (2 * padding)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-i", video_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-movflags", "+faststart",
        output_path,
    ]

    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def extract_thumbnail(
    video_path: str,
    output_path: str,
    timestamp: float,
) -> str:
    """Extract a single frame as a thumbnail."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(timestamp),
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        output_path,
    ]

    subprocess.run(cmd, check=True, capture_output=True)
    return output_path

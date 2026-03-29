"""
FFmpeg-based video clip extraction + annotated debug overlay clips.
"""

import logging
import subprocess
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


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


def extract_clip_annotated(
    video_path: str,
    output_path: str,
    event_timestamp: float,
    padding: float = 5.0,
    frame_annotations: dict | None = None,
    vid_stride: int = 1,
    video_fps: float = 30.0,
) -> str:
    """Extract a clip with debug overlays drawn on each frame.

    Draws: player bounding boxes (green=target, blue=other), track IDs,
    hoop bbox (yellow), ball position (orange), possession holder indicator.
    """
    start = max(0, event_timestamp - padding)
    duration = 2 * padding
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or video_fps
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    start_frame = int(start * fps)
    end_frame = int((start + duration) * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path + ".tmp.mp4", fourcc, fps, (w, h))

    frame_idx = start_frame
    last_ann = None

    while frame_idx < end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        # Find matching annotation (stride-adjusted frame index)
        stride_idx = frame_idx // vid_stride
        ann = None
        if frame_annotations:
            ann = frame_annotations.get(stride_idx)
            if ann is None:
                # Try ±1 stride frame
                ann = frame_annotations.get(stride_idx - 1) or frame_annotations.get(stride_idx + 1)
            if ann:
                last_ann = ann
            else:
                ann = last_ann  # Repeat last known annotation

        if ann:
            _draw_annotations(frame, ann)

        writer.write(frame)
        frame_idx += 1

    writer.release()
    cap.release()

    # Re-encode with ffmpeg for proper mp4 (movflags+faststart, h264)
    tmp_path = output_path + ".tmp.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", tmp_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-movflags", "+faststart",
        "-an",  # No audio for debug clips
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    Path(tmp_path).unlink(missing_ok=True)

    return output_path


def _draw_annotations(frame: np.ndarray, ann: dict) -> None:
    """Draw debug overlays on a single frame."""
    # Hoop (yellow)
    if ann.get("hoop"):
        hx1, hy1, hx2, hy2 = [int(v) for v in ann["hoop"]["bbox"]]
        cv2.rectangle(frame, (hx1, hy1), (hx2, hy2), (0, 255, 255), 2)
        cv2.putText(frame, "HOOP", (hx1, hy1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    # Ball (orange circle)
    if ann.get("ball"):
        bx1, by1, bx2, by2 = [int(v) for v in ann["ball"]["bbox"]]
        bcx, bcy = (bx1 + bx2) // 2, (by1 + by2) // 2
        radius = max(8, (bx2 - bx1) // 2)
        cv2.circle(frame, (bcx, bcy), radius, (0, 165, 255), 2)

    # Players
    holder_id = ann.get("possession", {}).get("holder_id", -1) if ann.get("possession") else -1
    for p in ann.get("players", []):
        x1, y1, x2, y2 = [int(v) for v in p["bbox"]]
        is_target = p["is_target"]
        tid = p["track_id"]

        if is_target:
            color = (0, 255, 0)  # Green for target
            thickness = 3
        elif tid == holder_id:
            color = (255, 200, 0)  # Cyan-ish for ball holder
            thickness = 2
        else:
            color = (255, 128, 0)  # Blue for others
            thickness = 1

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        # Label
        label = f"T{tid}"
        if is_target:
            label = f"TARGET T{tid}"
        if tid == holder_id:
            label += " [BALL]"

        label_y = max(y1 - 8, 15)
        cv2.putText(frame, label, (x1, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    # Possession status overlay (top-left)
    if ann.get("possession"):
        status = ann["possession"].get("ball_status", "?")
        cv2.putText(frame, f"Ball: {status}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)


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

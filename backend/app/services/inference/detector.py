"""
Player and ball detection using YOLOv8 with ByteTrack tracking.
"""

from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO


@dataclass
class Detection:
    track_id: int
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    confidence: float
    class_name: str  # "person", "ball"
    frame_idx: int


class PlayerBallDetector:
    def __init__(self, model_path: str = "yolov8x.pt"):
        self.model = YOLO(model_path)

    def detect_frame(self, frame: np.ndarray, frame_idx: int) -> list[Detection]:
        """Run detection + tracking on a single frame."""
        results = self.model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0, 32],  # person=0, sports ball=32 (COCO)
            conf=0.3,
            verbose=False,
        )

        detections = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                track_id = int(box.id[0]) if box.id is not None else -1
                cls = int(box.cls[0])
                class_name = "person" if cls == 0 else "ball"
                detections.append(
                    Detection(
                        track_id=track_id,
                        bbox=tuple(box.xyxy[0].tolist()),
                        confidence=float(box.conf[0]),
                        class_name=class_name,
                        frame_idx=frame_idx,
                    )
                )
        return detections

    def process_video(self, video_path: str, sample_fps: int = 10):
        """Process entire video, yielding detections per frame."""
        results = self.model.track(
            video_path,
            stream=True,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0, 32],
            conf=0.3,
            verbose=False,
        )

        for frame_idx, result in enumerate(results):
            detections = []
            if result.boxes is not None:
                for box in result.boxes:
                    track_id = int(box.id[0]) if box.id is not None else -1
                    cls = int(box.cls[0])
                    class_name = "person" if cls == 0 else "ball"
                    detections.append(
                        Detection(
                            track_id=track_id,
                            bbox=tuple(box.xyxy[0].tolist()),
                            confidence=float(box.conf[0]),
                            class_name=class_name,
                            frame_idx=frame_idx,
                        )
                    )
            yield frame_idx, detections

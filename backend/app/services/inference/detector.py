"""
Player and ball detection using YOLOv8 with BoT-SORT tracking.
Hoop detection using a basketball-specific YOLO model.
"""

import logging
from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    track_id: int
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    confidence: float
    class_name: str  # "person", "ball", "hoop"
    frame_idx: int


class PlayerBallDetector:
    """Dual-model detector: COCO YOLOv8x for person+ball, basketball YOLO for hoop."""

    def __init__(self, model_path: str = "yolov8x.pt", hoop_model_path: str | None = None):
        self.model = YOLO(model_path)
        self.hoop_model = YOLO(hoop_model_path) if hoop_model_path else None
        if self.hoop_model:
            logger.info(f"Hoop model loaded: {hoop_model_path} classes={self.hoop_model.names}")

    def detect_frame(self, frame: np.ndarray, frame_idx: int) -> list[Detection]:
        """Run detection + tracking on a single frame."""
        # COCO model: person (0) + sports ball (32)
        results = self.model.track(
            frame,
            persist=True,
            tracker="botsort.yaml",
            classes=[0, 32],
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

        # Hoop model (no tracking needed — hoops don't move)
        if self.hoop_model:
            hoop_results = self.hoop_model(frame, conf=0.3, verbose=False)
            for result in hoop_results:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    cls = int(box.cls[0])
                    # Class 1 = Basketball Hoop in the shot-tracker model
                    if cls == 1:
                        detections.append(
                            Detection(
                                track_id=-1,
                                bbox=tuple(box.xyxy[0].tolist()),
                                confidence=float(box.conf[0]),
                                class_name="hoop",
                                frame_idx=frame_idx,
                            )
                        )
                    elif cls == 0:
                        # Basketball class — use as supplementary ball detection
                        conf = float(box.conf[0])
                        if conf > 0.4:  # Higher threshold for supplementary detections
                            detections.append(
                                Detection(
                                    track_id=-1,
                                    bbox=tuple(box.xyxy[0].tolist()),
                                    confidence=conf,
                                    class_name="ball",
                                    frame_idx=frame_idx,
                                )
                            )

        return detections

    def process_video(self, video_path: str, vid_stride: int = 1):
        """Process entire video, yielding detections per frame.

        vid_stride: process every Nth frame (2 = skip every other frame).
        """
        results = self.model.track(
            video_path,
            stream=True,
            persist=True,
            tracker="botsort.yaml",
            classes=[0, 32],
            conf=0.3,
            verbose=False,
            vid_stride=vid_stride,
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

            # Run hoop model on every frame (cheap — no tracking overhead)
            if self.hoop_model and result.orig_img is not None:
                hoop_results = self.hoop_model(result.orig_img, conf=0.3, verbose=False)
                for hr in hoop_results:
                    if hr.boxes is None:
                        continue
                    for box in hr.boxes:
                        cls = int(box.cls[0])
                        if cls == 1:
                            detections.append(
                                Detection(
                                    track_id=-1,
                                    bbox=tuple(box.xyxy[0].tolist()),
                                    confidence=float(box.conf[0]),
                                    class_name="hoop",
                                    frame_idx=frame_idx,
                                )
                            )
                        elif cls == 0 and float(box.conf[0]) > 0.4:
                            detections.append(
                                Detection(
                                    track_id=-1,
                                    bbox=tuple(box.xyxy[0].tolist()),
                                    confidence=float(box.conf[0]),
                                    class_name="ball",
                                    frame_idx=frame_idx,
                                )
                            )

            yield frame_idx, detections, result.orig_img

"""
Pose estimation using YOLOv8-Pose for basketball action classification.

Extracts COCO skeleton keypoints and classifies poses as:
  - "shooting": wrist significantly above shoulder + elbow above shoulder
  - "dribbling": wrist below hip level
  - "other": neither detected

Uses yolov8m-pose (medium) to keep VRAM in check alongside YOLOv8x detection + hoop model.
"""

import ml.patch_platform  # noqa: F401  — must be first import (WMI hang workaround)

import logging
from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# COCO pose keypoint indices
KP_NOSE = 0
KP_LEFT_SHOULDER = 5
KP_RIGHT_SHOULDER = 6
KP_LEFT_ELBOW = 7
KP_RIGHT_ELBOW = 8
KP_LEFT_WRIST = 9
KP_RIGHT_WRIST = 10
KP_LEFT_HIP = 11
KP_RIGHT_HIP = 12


@dataclass
class PoseResult:
    """Pose estimation result for a single detected person."""
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    keypoints: np.ndarray  # shape (17, 3) — x, y, confidence per keypoint
    action: str  # "shooting", "dribbling", "other"
    action_confidence: float  # heuristic confidence for the classified action


class PoseEstimator:
    """YOLOv8-Pose wrapper for basketball pose classification."""

    def __init__(self, model_path: str = "yolov8m-pose.pt", conf: float = 0.3):
        self.model = YOLO(model_path)
        self.conf = conf
        logger.info(f"Pose model loaded: {model_path}")

    def estimate(self, frame: np.ndarray) -> list[PoseResult]:
        """Run pose estimation on a single frame.

        Returns a PoseResult per detected person with keypoints and action classification.
        """
        results = self.model(frame, conf=self.conf, verbose=False)

        pose_results = []
        for result in results:
            if result.keypoints is None or result.boxes is None:
                continue

            keypoints_data = result.keypoints.data  # (N, 17, 3)
            boxes = result.boxes.xyxy  # (N, 4)

            for i in range(len(boxes)):
                kps = keypoints_data[i].cpu().numpy()  # (17, 3)
                bbox = tuple(boxes[i].cpu().tolist())
                action, confidence = self._classify_action(kps)
                pose_results.append(PoseResult(
                    bbox=bbox,
                    keypoints=kps,
                    action=action,
                    action_confidence=confidence,
                ))

        return pose_results

    def estimate_for_track(
        self,
        frame: np.ndarray,
        track_bbox: tuple[float, float, float, float],
        iou_threshold: float = 0.3,
    ) -> PoseResult | None:
        """Run pose estimation and return the result matching a specific tracked player bbox.

        Matches by best IoU overlap between pose detection bbox and the given track_bbox.
        """
        poses = self.estimate(frame)
        if not poses:
            return None

        best_pose = None
        best_iou = 0.0
        for pose in poses:
            iou = self._compute_iou(pose.bbox, track_bbox)
            if iou > best_iou and iou >= iou_threshold:
                best_iou = iou
                best_pose = pose

        return best_pose

    def _classify_action(self, kps: np.ndarray) -> tuple[str, float]:
        """Classify pose as shooting, dribbling, or other based on keypoint geometry.

        Args:
            kps: (17, 3) array — x, y, confidence per COCO keypoint.

        Returns:
            (action_name, confidence) tuple.
        """
        # Minimum keypoint confidence to consider a joint "visible"
        vis_thresh = 0.3

        shooting_conf = self._check_shooting(kps, vis_thresh)
        dribbling_conf = self._check_dribbling(kps, vis_thresh)

        if shooting_conf > dribbling_conf and shooting_conf > 0.0:
            return "shooting", shooting_conf
        elif dribbling_conf > 0.0:
            return "dribbling", dribbling_conf
        else:
            return "other", 0.0

    def _check_shooting(self, kps: np.ndarray, vis_thresh: float) -> float:
        """Shooting heuristic: either wrist significantly above corresponding shoulder,
        AND elbow above shoulder.

        In image coordinates, "above" means smaller y value.
        """
        best_conf = 0.0

        # Check both left and right sides
        for side in ("left", "right"):
            if side == "left":
                shoulder, elbow, wrist = KP_LEFT_SHOULDER, KP_LEFT_ELBOW, KP_LEFT_WRIST
            else:
                shoulder, elbow, wrist = KP_RIGHT_SHOULDER, KP_RIGHT_ELBOW, KP_RIGHT_WRIST

            s_y, s_conf = kps[shoulder][1], kps[shoulder][2]
            e_y, e_conf = kps[elbow][1], kps[elbow][2]
            w_y, w_conf = kps[wrist][1], kps[wrist][2]

            if s_conf < vis_thresh or e_conf < vis_thresh or w_conf < vis_thresh:
                continue

            # Compute torso height as reference scale (shoulder to hip)
            hip_idx = KP_LEFT_HIP if side == "left" else KP_RIGHT_HIP
            h_y, h_conf = kps[hip_idx][1], kps[hip_idx][2]
            if h_conf < vis_thresh:
                continue

            torso_height = abs(h_y - s_y)
            if torso_height < 10:  # Too small to be meaningful
                continue

            # Wrist must be above shoulder by at least 15% of torso height
            wrist_above_shoulder = s_y - w_y
            elbow_above_shoulder = s_y - e_y

            if wrist_above_shoulder > 0.15 * torso_height and elbow_above_shoulder > 0:
                # Confidence based on how high the wrist is above the shoulder
                conf = min(1.0, wrist_above_shoulder / torso_height)
                # Average with keypoint confidences
                kp_conf = min(s_conf, e_conf, w_conf)
                combined = conf * 0.7 + kp_conf * 0.3
                best_conf = max(best_conf, combined)

        return best_conf

    def _check_dribbling(self, kps: np.ndarray, vis_thresh: float) -> float:
        """Dribbling heuristic: either wrist below corresponding hip.

        In image coordinates, "below" means larger y value.
        """
        best_conf = 0.0

        for side in ("left", "right"):
            if side == "left":
                wrist, hip = KP_LEFT_WRIST, KP_LEFT_HIP
            else:
                wrist, hip = KP_RIGHT_WRIST, KP_RIGHT_HIP

            w_y, w_conf = kps[wrist][1], kps[wrist][2]
            h_y, h_conf = kps[hip][1], kps[hip][2]

            if w_conf < vis_thresh or h_conf < vis_thresh:
                continue

            # Also need shoulder for scale
            shoulder_idx = KP_LEFT_SHOULDER if side == "left" else KP_RIGHT_SHOULDER
            s_y, s_conf = kps[shoulder_idx][1], kps[shoulder_idx][2]
            if s_conf < vis_thresh:
                continue

            torso_height = abs(h_y - s_y)
            if torso_height < 10:
                continue

            wrist_below_hip = w_y - h_y
            if wrist_below_hip > 0:
                conf = min(1.0, wrist_below_hip / (0.5 * torso_height))
                kp_conf = min(w_conf, h_conf)
                combined = conf * 0.7 + kp_conf * 0.3
                best_conf = max(best_conf, combined)

        return best_conf

    @staticmethod
    def _compute_iou(
        box1: tuple[float, float, float, float],
        box2: tuple[float, float, float, float],
    ) -> float:
        """Compute IoU between two bboxes (x1, y1, x2, y2)."""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        inter = max(0, x2 - x1) * max(0, y2 - y1)
        if inter == 0:
            return 0.0

        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter
        return inter / union if union > 0 else 0.0

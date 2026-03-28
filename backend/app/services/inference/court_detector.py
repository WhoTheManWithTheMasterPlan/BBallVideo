"""
Basketball court keypoint detector using YOLOv8-pose.

Detects court landmarks (corners, free throw lines, midcourt) and computes
per-frame homography to map pixel coordinates to normalized court coordinates.

Model: YOLOv8x-pose fine-tuned on basketball court keypoint dataset.
Expected 18 keypoints per frame corresponding to court landmarks.
"""

import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = "ml/models/court-detector/best.pt"

# Standard basketball court dimensions (meters, FIBA)
COURT_WIDTH_M = 28.0   # sideline to sideline
COURT_HEIGHT_M = 15.0  # baseline to baseline

# Tactical view pixel dimensions (for internal homography computation)
TACTIC_W = 300
TACTIC_H = 161

# 18 reference keypoints on the tactical court image (pixel coords).
# These correspond to the keypoints the YOLOv8-pose model detects, in order.
# Layout follows HanaFEKI/AI_BasketBall_Analysis_v1 convention:
#   0-5:   Left baseline (bottom-left to top-left)
#   6-7:   Midcourt line (bottom, top)
#   8-9:   Left free throw corners
#   10-15: Right baseline (bottom-right to top-right, reversed)
#   16-17: Right free throw corners
COURT_REFERENCE_POINTS = np.array([
    # Left edge (baseline), bottom to top
    (0, 0),                                                                              # 0: bottom-left corner
    (0, int((0.91 / COURT_HEIGHT_M) * TACTIC_H)),                                       # 1: left baseline near-bottom
    (0, int((5.18 / COURT_HEIGHT_M) * TACTIC_H)),                                       # 2: left paint bottom
    (0, int((10.0 / COURT_HEIGHT_M) * TACTIC_H)),                                       # 3: left paint top
    (0, int((14.1 / COURT_HEIGHT_M) * TACTIC_H)),                                       # 4: left baseline near-top
    (0, TACTIC_H),                                                                       # 5: top-left corner

    # Midcourt line
    (TACTIC_W // 2, TACTIC_H),                                                          # 6: midcourt bottom
    (TACTIC_W // 2, 0),                                                                 # 7: midcourt top

    # Left free throw line corners
    (int((5.79 / COURT_WIDTH_M) * TACTIC_W), int((5.18 / COURT_HEIGHT_M) * TACTIC_H)), # 8: left FT bottom
    (int((5.79 / COURT_WIDTH_M) * TACTIC_W), int((10.0 / COURT_HEIGHT_M) * TACTIC_H)), # 9: left FT top

    # Right edge (baseline), bottom to top
    (TACTIC_W, TACTIC_H),                                                               # 10: bottom-right corner
    (TACTIC_W, int((14.1 / COURT_HEIGHT_M) * TACTIC_H)),                                # 11: right baseline near-bottom
    (TACTIC_W, int((10.0 / COURT_HEIGHT_M) * TACTIC_H)),                                # 12: right paint top
    (TACTIC_W, int((5.18 / COURT_HEIGHT_M) * TACTIC_H)),                                # 13: right paint bottom
    (TACTIC_W, int((0.91 / COURT_HEIGHT_M) * TACTIC_H)),                                # 14: right baseline near-top
    (TACTIC_W, 0),                                                                       # 15: top-right corner

    # Right free throw line corners
    (int(((COURT_WIDTH_M - 5.79) / COURT_WIDTH_M) * TACTIC_W),
     int((5.18 / COURT_HEIGHT_M) * TACTIC_H)),                                          # 16: right FT bottom
    (int(((COURT_WIDTH_M - 5.79) / COURT_WIDTH_M) * TACTIC_W),
     int((10.0 / COURT_HEIGHT_M) * TACTIC_H)),                                          # 17: right FT top
], dtype=np.float32)


class CourtDetector:
    """Detects court keypoints and computes pixel-to-court homography per frame."""

    def __init__(self, weights_path: str | None = None, conf_threshold: float = 0.5):
        from ultralytics import YOLO

        if weights_path is None:
            # __file__ = backend/app/services/inference/court_detector.py
            # 4 parents = backend/, 5 parents = project root
            project_root = Path(__file__).parent.parent.parent.parent.parent
            candidate = project_root / DEFAULT_WEIGHTS
            if candidate.exists():
                weights_path = str(candidate)
            else:
                raise FileNotFoundError(
                    f"Court detector weights not found at {candidate}. "
                    f"Train with YOLOv8-pose on a basketball court keypoint dataset."
                )

        self.model = YOLO(weights_path)
        self.conf_threshold = conf_threshold
        self.last_valid_H: np.ndarray | None = None
        self.last_valid_keypoints: np.ndarray | None = None
        logger.info(f"Court detector loaded from {weights_path}")

    def detect_keypoints(self, frame: np.ndarray) -> np.ndarray | None:
        """
        Detect court keypoints in a single frame.

        Returns:
            Nx2 array of keypoint pixel coordinates, or None if detection fails.
            Zero-valued keypoints indicate low confidence / not detected.
        """
        results = self.model.predict(frame, conf=self.conf_threshold, verbose=False)
        if not results or not results[0].keypoints:
            return None

        kps = results[0].keypoints
        if not hasattr(kps, "confidence") or kps.xy is None:
            return None

        keypoints = []
        for idx, (point, conf) in enumerate(zip(kps.xy[0], kps.confidence[0])):
            if conf >= self.conf_threshold:
                keypoints.append(point.cpu().numpy())
            elif self.last_valid_keypoints is not None and idx < len(self.last_valid_keypoints):
                # Fall back to last valid detection for this keypoint
                keypoints.append(self.last_valid_keypoints[idx])
            else:
                keypoints.append(np.array([0.0, 0.0]))

        keypoints = np.array(keypoints, dtype=np.float32)

        # Update last valid if we got reasonable detections
        valid_count = np.sum((keypoints[:, 0] > 0) & (keypoints[:, 1] > 0))
        if valid_count >= 4:
            self.last_valid_keypoints = keypoints.copy()

        return keypoints

    def compute_homography(self, keypoints: np.ndarray) -> np.ndarray | None:
        """
        Compute homography from detected keypoints to court reference points.

        Returns:
            3x3 homography matrix, or None if insufficient keypoints.
        """
        if keypoints is None or len(keypoints) != len(COURT_REFERENCE_POINTS):
            return self.last_valid_H

        # Filter to valid (non-zero) keypoints
        valid_mask = (keypoints[:, 0] > 0) & (keypoints[:, 1] > 0)
        if np.sum(valid_mask) < 4:
            return self.last_valid_H

        src_pts = keypoints[valid_mask]
        dst_pts = COURT_REFERENCE_POINTS[valid_mask]

        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0, maxIters=2000)
        if H is None:
            return self.last_valid_H

        # Fix horizontal flip
        if np.linalg.det(H[:2, :2]) < 0:
            H[:, 0] *= -1

        # Check reprojection error
        projected = cv2.perspectiveTransform(
            src_pts.reshape(-1, 1, 2), H
        ).reshape(-1, 2)
        error = np.mean(np.linalg.norm(projected - dst_pts, axis=1))
        if error > 40.0:
            return self.last_valid_H

        # Blend with previous for temporal smoothing
        if self.last_valid_H is not None:
            alpha = 0.85
            H = alpha * self.last_valid_H + (1 - alpha) * H
            H /= H[-1, -1]

        self.last_valid_H = H
        return H

    def pixel_to_court(
        self, H: np.ndarray, pixel_x: float, pixel_y: float
    ) -> tuple[float, float] | None:
        """
        Map a pixel coordinate to normalized court coordinates (0-1).

        Args:
            H: 3x3 homography matrix from compute_homography()
            pixel_x, pixel_y: pixel position in the frame (e.g. player foot position)

        Returns:
            (court_x, court_y) normalized 0-1, or None if out of bounds.
        """
        point = np.array([[[pixel_x, pixel_y]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(point, H)
        x, y = float(transformed[0][0][0]), float(transformed[0][0][1])

        # Normalize to 0-1 using tactical view dimensions
        norm_x = x / TACTIC_W
        norm_y = y / TACTIC_H

        # Reject if out of bounds (with small margin)
        if norm_x < -0.05 or norm_x > 1.05 or norm_y < -0.05 or norm_y > 1.05:
            return None

        return (max(0.0, min(1.0, norm_x)), max(0.0, min(1.0, norm_y)))

    def get_foot_position(self, bbox: tuple[float, float, float, float]) -> tuple[float, float]:
        """Get foot position (bottom center) from a bounding box."""
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2, y2)

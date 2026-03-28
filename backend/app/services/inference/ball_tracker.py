"""
Kalman filter-based ball tracker for interpolating ball position across detection gaps.
Solves the core problem: YOLO frequently loses the basketball for several frames mid-flight,
breaking the up→down trajectory needed for shot detection.
"""

import logging
from collections import deque
from dataclasses import dataclass

import numpy as np
from filterpy.kalman import KalmanFilter

logger = logging.getLogger(__name__)


@dataclass
class BallState:
    cx: float
    cy: float
    frame_idx: int
    detected: bool  # True = real detection, False = Kalman prediction
    confidence: float


class BallTracker:
    """Tracks ball position with Kalman filter interpolation across detection gaps.

    State vector: [cx, cy, vx, vy] — position + velocity.
    When YOLO detects the ball, we update the filter.
    When YOLO misses, we predict forward using the filter's velocity estimate.
    """

    MAX_PREDICT_FRAMES = 15  # Don't predict more than 15 frames without a detection (~0.5s at 30fps)
    MIN_CONFIDENCE_FOR_UPDATE = 0.15  # Accept low-confidence YOLO ball detections

    def __init__(self):
        self.kf = self._init_kalman()
        self.active = False
        self._frames_since_detection = 0
        self.history: deque[BallState] = deque(maxlen=120)  # ~4 seconds at 30fps

    def _init_kalman(self) -> KalmanFilter:
        """Initialize a 2D constant-velocity Kalman filter."""
        kf = KalmanFilter(dim_x=4, dim_z=2)

        # State transition: constant velocity model
        # [cx, cy, vx, vy] -> [cx + vx*dt, cy + vy*dt, vx, vy]
        dt = 1.0  # frame-to-frame
        kf.F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=np.float64)

        # Measurement: we observe cx, cy
        kf.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
        ], dtype=np.float64)

        # Measurement noise — ball detections are noisy
        kf.R = np.array([
            [15.0, 0],
            [0, 15.0],
        ], dtype=np.float64)

        # Process noise — ball accelerates (gravity, bounces, shots)
        q = 25.0  # Higher = more responsive to changes, less smooth
        kf.Q = np.array([
            [q, 0, 0, 0],
            [0, q, 0, 0],
            [0, 0, q * 4, 0],  # Velocity changes faster
            [0, 0, 0, q * 4],
        ], dtype=np.float64)

        # Initial covariance — high uncertainty
        kf.P *= 500.0

        return kf

    def update(self, ball_cx: float | None, ball_cy: float | None,
               frame_idx: int, confidence: float = 0.0) -> BallState | None:
        """Update tracker with a detection (or None if ball not seen).

        Returns the current best estimate of ball position, or None if tracker is inactive.
        """
        if ball_cx is not None and ball_cy is not None and confidence >= self.MIN_CONFIDENCE_FOR_UPDATE:
            # Real detection — update Kalman filter
            if not self.active:
                # First detection — initialize state
                self.kf.x = np.array([ball_cx, ball_cy, 0, 0], dtype=np.float64)
                self.active = True
            else:
                self.kf.predict()
                self.kf.update(np.array([ball_cx, ball_cy], dtype=np.float64))

            self._frames_since_detection = 0
            state = BallState(
                cx=float(self.kf.x[0]),
                cy=float(self.kf.x[1]),
                frame_idx=frame_idx,
                detected=True,
                confidence=confidence,
            )
            self.history.append(state)
            return state

        elif self.active and self._frames_since_detection < self.MAX_PREDICT_FRAMES:
            # No detection — predict using Kalman velocity
            self.kf.predict()
            self._frames_since_detection += 1

            state = BallState(
                cx=float(self.kf.x[0]),
                cy=float(self.kf.x[1]),
                frame_idx=frame_idx,
                detected=False,
                confidence=max(0.1, confidence - 0.05 * self._frames_since_detection),
            )
            self.history.append(state)
            return state

        else:
            # Too many frames without detection — go inactive
            if self.active and self._frames_since_detection >= self.MAX_PREDICT_FRAMES:
                self.active = False
            return None

    def get_recent_trajectory(self, n_frames: int = 30) -> list[BallState]:
        """Get the last N ball states (detected + predicted)."""
        return list(self.history)[-n_frames:]

    def reset(self):
        """Reset the tracker."""
        self.kf = self._init_kalman()
        self.active = False
        self._frames_since_detection = 0
        self.history.clear()

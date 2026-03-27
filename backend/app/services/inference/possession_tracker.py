"""
Continuous ball possession tracking.
Determines which player has the ball on every frame.
"""

import logging
import math
from dataclasses import dataclass, field

from app.services.inference.detector import Detection

logger = logging.getLogger(__name__)


@dataclass
class PossessionState:
    holder_track_id: int  # -1 if no one
    holder_team: str | None
    ball_status: str  # "held", "in_air", "not_visible"
    last_holder_track_id: int  # who had it before
    last_holder_team: str | None
    frames_held: int  # consecutive frames current holder has had it


class PossessionTracker:
    """Frame-by-frame ball possession state machine."""

    HOLD_DISTANCE = 80  # pixels — ball within this of player bbox = held
    CONTAINMENT_THRESHOLD = 0.5  # ball bbox overlap ratio for definite possession
    MIN_FRAMES_TO_CONFIRM = 8  # consecutive frames before confirming possession change

    def __init__(self):
        self._current_holder: int = -1
        self._current_team: str | None = None
        self._last_holder: int = -1
        self._last_team: str | None = None
        self._candidate: int = -1
        self._candidate_frames: int = 0
        self._frames_held: int = 0

    def update(
        self,
        detections: list[Detection],
        player_teams: dict[int, str],
    ) -> PossessionState:
        """Update possession state for one frame.

        Args:
            detections: all detections for this frame
            player_teams: track_id -> team_name mapping
        """
        ball_dets = [d for d in detections if d.class_name == "ball"]
        person_dets = [d for d in detections if d.class_name == "person" and d.track_id >= 0]

        if not ball_dets:
            # Ball not visible — keep last known state
            return PossessionState(
                holder_track_id=self._current_holder,
                holder_team=self._current_team,
                ball_status="not_visible",
                last_holder_track_id=self._last_holder,
                last_holder_team=self._last_team,
                frames_held=self._frames_held,
            )

        # Use highest-confidence ball detection
        ball = max(ball_dets, key=lambda d: d.confidence)
        ball_cx = (ball.bbox[0] + ball.bbox[2]) / 2
        ball_cy = (ball.bbox[1] + ball.bbox[3]) / 2

        # Find nearest player
        best_id = -1
        best_dist = float("inf")

        for det in person_dets:
            dist = self._player_ball_distance(det, ball_cx, ball_cy)
            if dist < best_dist:
                best_dist = dist
                best_id = det.track_id

        if best_id >= 0 and best_dist < self.HOLD_DISTANCE:
            # Someone is close enough to have the ball
            if best_id == self._candidate:
                self._candidate_frames += 1
            else:
                self._candidate = best_id
                self._candidate_frames = 1

            if self._candidate_frames >= self.MIN_FRAMES_TO_CONFIRM:
                if self._current_holder != best_id:
                    # Possession change
                    self._last_holder = self._current_holder
                    self._last_team = self._current_team
                    self._current_holder = best_id
                    self._current_team = player_teams.get(best_id)
                    self._frames_held = 0

                self._frames_held += 1

            return PossessionState(
                holder_track_id=self._current_holder,
                holder_team=self._current_team,
                ball_status="held",
                last_holder_track_id=self._last_holder,
                last_holder_team=self._last_team,
                frames_held=self._frames_held,
            )

        # Ball visible but not near any player
        return PossessionState(
            holder_track_id=self._current_holder,
            holder_team=self._current_team,
            ball_status="in_air",
            last_holder_track_id=self._last_holder,
            last_holder_team=self._last_team,
            frames_held=self._frames_held,
        )

    @staticmethod
    def _player_ball_distance(player: Detection, ball_cx: float, ball_cy: float) -> float:
        """Minimum distance from ball center to player bbox edges/center."""
        x1, y1, x2, y2 = player.bbox
        # Clamp ball position to bbox — if inside, distance is 0
        closest_x = max(x1, min(ball_cx, x2))
        closest_y = max(y1, min(ball_cy, y2))
        return math.sqrt((ball_cx - closest_x) ** 2 + (ball_cy - closest_y) ** 2)

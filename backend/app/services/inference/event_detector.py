"""
Basketball event detection: made baskets, steals, assists.
Derives events from possession state + hoop detections.
"""

import logging
import math
from collections import deque
from dataclasses import dataclass

from app.services.inference.detector import Detection
from app.services.inference.possession_tracker import PossessionState

logger = logging.getLogger(__name__)


@dataclass
class BasketballEvent:
    event_type: str  # "made_basket", "steal", "assist"
    frame_idx: int
    timestamp: float
    player_track_id: int
    confidence: float
    metadata: dict


class ShotTracker:
    """Tracks ball trajectory relative to hoop to detect made baskets."""

    def __init__(self):
        self.ball_positions: deque = deque(maxlen=60)  # (cx, cy, frame_idx)
        self.hoop_position: tuple[float, float, float, float] | None = None  # best hoop bbox
        self._ball_above_hoop = False
        self._above_frame = 0

    def update_hoop(self, hoop_dets: list[Detection]):
        """Update hoop position from detections. Use highest confidence."""
        if hoop_dets:
            best = max(hoop_dets, key=lambda d: d.confidence)
            self.hoop_position = best.bbox

    def update_ball(self, ball_dets: list[Detection], frame_idx: int):
        """Track ball position."""
        if ball_dets:
            best = max(ball_dets, key=lambda d: d.confidence)
            cx = (best.bbox[0] + best.bbox[2]) / 2
            cy = (best.bbox[1] + best.bbox[3]) / 2
            self.ball_positions.append((cx, cy, frame_idx))

    def check_made_basket(self, frame_idx: int) -> float:
        """Check if ball trajectory indicates a made basket.

        Returns confidence (0-1), or 0 if no shot detected.
        Uses the avishah3 approach: ball goes above hoop, then below = shot attempt.
        If ball path intersects rim horizontally = made basket.
        """
        if not self.hoop_position or len(self.ball_positions) < 3:
            return 0.0

        hx1, hy1, hx2, hy2 = self.hoop_position
        hoop_cx = (hx1 + hx2) / 2
        hoop_cy = (hy1 + hy2) / 2
        hoop_w = hx2 - hx1
        hoop_h = hy2 - hy1
        rim_top = hy1 - 0.5 * hoop_h

        ball_cx, ball_cy, _ = self.ball_positions[-1]

        # Check: is ball currently near/above hoop region?
        near_hoop_x = abs(ball_cx - hoop_cx) < 4 * hoop_w

        if not near_hoop_x:
            self._ball_above_hoop = False
            return 0.0

        # Track up→down transition
        if ball_cy < rim_top and not self._ball_above_hoop:
            self._ball_above_hoop = True
            self._above_frame = frame_idx

        if self._ball_above_hoop and ball_cy > hy2:
            # Ball went from above to below hoop — shot attempt
            self._ball_above_hoop = False

            # Check if ball path crosses through the rim
            # Find the last position above rim and first below
            above_pos = None
            below_pos = None
            for cx, cy, fidx in reversed(self.ball_positions):
                if cy < hy1 and above_pos is None:
                    above_pos = (cx, cy)
                if cy > hy2 and below_pos is None:
                    below_pos = (cx, cy)
                if above_pos and below_pos:
                    break

            if above_pos and below_pos and above_pos[1] != below_pos[1]:
                # Linear interpolation: where does ball cross rim height?
                t = (hoop_cy - above_pos[1]) / (below_pos[1] - above_pos[1])
                predicted_x = above_pos[0] + t * (below_pos[0] - above_pos[0])

                rim_left = hx1 - 0.3 * hoop_w
                rim_right = hx2 + 0.3 * hoop_w

                if rim_left < predicted_x < rim_right:
                    return 0.8  # Made basket
                else:
                    return 0.0  # Miss — ball didn't go through rim

        return 0.0


class EventDetector:
    """Detects made baskets, steals, and assists from possession + detection data."""

    STEAL_COOLDOWN_FRAMES = 60  # Don't detect steals within N frames of each other
    ASSIST_WINDOW_FRAMES = 150  # ~5 seconds at 30fps — pass before basket = assist

    def __init__(self):
        self.shot_tracker = ShotTracker()
        self.possession_history: deque = deque(maxlen=300)  # (frame_idx, PossessionState)
        self._last_steal_frame = -999
        self._last_made_basket_frame = -999

    def update(
        self,
        frame_idx: int,
        timestamp: float,
        detections: list[Detection],
        possession: PossessionState,
    ) -> list[BasketballEvent]:
        """Process one frame and return any detected events."""
        events = []

        hoop_dets = [d for d in detections if d.class_name == "hoop"]
        ball_dets = [d for d in detections if d.class_name == "ball"]

        self.shot_tracker.update_hoop(hoop_dets)
        self.shot_tracker.update_ball(ball_dets, frame_idx)
        self.possession_history.append((frame_idx, possession))

        # Check for made basket
        shot_conf = self.shot_tracker.check_made_basket(frame_idx)
        if shot_conf > 0.5 and (frame_idx - self._last_made_basket_frame) > 90:
            scorer_id = possession.last_holder_track_id if possession.ball_status == "in_air" else possession.holder_track_id
            if scorer_id >= 0:
                self._last_made_basket_frame = frame_idx
                events.append(BasketballEvent(
                    event_type="made_basket",
                    frame_idx=frame_idx,
                    timestamp=timestamp,
                    player_track_id=scorer_id,
                    confidence=shot_conf,
                    metadata={"scorer_track_id": scorer_id},
                ))

                # Check for assist — was there a same-team pass before this basket?
                assist_event = self._check_assist(frame_idx, timestamp, scorer_id)
                if assist_event:
                    events.append(assist_event)

        # Check for steal
        steal_event = self._check_steal(frame_idx, timestamp, possession)
        if steal_event:
            events.append(steal_event)

        return events

    def _check_steal(
        self, frame_idx: int, timestamp: float, possession: PossessionState
    ) -> BasketballEvent | None:
        """Detect steal: possession changes teams without a shot attempt."""
        if (frame_idx - self._last_steal_frame) < self.STEAL_COOLDOWN_FRAMES:
            return None

        if (
            possession.holder_track_id >= 0
            and possession.last_holder_track_id >= 0
            and possession.holder_team is not None
            and possession.last_holder_team is not None
            and possession.holder_team != possession.last_holder_team
            and possession.frames_held == 0  # Just changed
        ):
            # Check that ball wasn't "in_air" for too long (would be a rebound, not steal)
            recent_air_frames = sum(
                1 for _, ps in self.possession_history
                if ps.ball_status == "in_air"
                and frame_idx - _ < 30  # last second
            )
            if recent_air_frames < 15:  # Less than half a second of air time
                self._last_steal_frame = frame_idx
                return BasketballEvent(
                    event_type="steal",
                    frame_idx=frame_idx,
                    timestamp=timestamp,
                    player_track_id=possession.holder_track_id,
                    confidence=0.7,
                    metadata={
                        "stealer_track_id": possession.holder_track_id,
                        "victim_track_id": possession.last_holder_track_id,
                    },
                )
        return None

    def _check_assist(
        self, frame_idx: int, timestamp: float, scorer_track_id: int
    ) -> BasketballEvent | None:
        """Check if there was a same-team pass leading to this made basket."""
        # Look back through possession history for a same-team possession change
        scorer_team = None
        prev_holder = None

        for hist_frame, ps in reversed(self.possession_history):
            if frame_idx - hist_frame > self.ASSIST_WINDOW_FRAMES:
                break

            if ps.holder_track_id == scorer_track_id and scorer_team is None:
                scorer_team = ps.holder_team

            # Found a different player on the same team who had the ball before the scorer
            if (
                scorer_team
                and ps.holder_track_id != scorer_track_id
                and ps.holder_track_id >= 0
                and ps.holder_team == scorer_team
            ):
                prev_holder = ps.holder_track_id
                break

        if prev_holder is not None and prev_holder != scorer_track_id:
            return BasketballEvent(
                event_type="assist",
                frame_idx=frame_idx,
                timestamp=timestamp,
                player_track_id=prev_holder,
                confidence=0.6,
                metadata={
                    "assister_track_id": prev_holder,
                    "scorer_track_id": scorer_track_id,
                },
            )
        return None

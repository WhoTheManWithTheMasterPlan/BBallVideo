"""
Basketball event detection: made baskets, steals, assists.
Derives events from possession state + hoop detections + Kalman ball tracking.
"""

import logging
import math
from collections import deque
from dataclasses import dataclass

from app.services.inference.ball_tracker import BallTracker, BallState
from app.services.inference.detector import Detection
from app.services.inference.possession_tracker import PossessionState

logger = logging.getLogger(__name__)


@dataclass
class BasketballEvent:
    event_type: str  # "made_basket", "missed_basket", "steal", "assist", "rebound"
    frame_idx: int
    timestamp: float
    player_track_id: int
    confidence: float
    metadata: dict


class ShotTracker:
    """Tracks ball trajectory relative to hoop to detect made baskets.

    Uses Kalman-filtered ball positions for smooth trajectories across detection gaps.
    Three detection methods (any one triggers a made basket):
      1. Classic up→down: ball goes above hoop then below, trajectory crosses rim
      2. Proximity burst: ball appears inside/very near hoop bbox multiple times in short window
      3. Velocity spike: ball has sudden downward velocity near hoop (falling through net)
    """

    def __init__(self):
        self.ball_tracker = BallTracker()
        self.hoop_position: tuple[float, float, float, float] | None = None
        self.hoop_confidence: float = 0.0
        self._ball_above_hoop = False
        self._above_frame = 0
        # Proximity tracking: count frames where ball is very close to hoop
        self._near_hoop_frames: deque = deque(maxlen=30)
        # Shot attempt tracking for missed basket detection
        self._last_shot_attempt_frame = -999
        self._shot_attempt_pending = False  # True when up→down near hoop but not yet classified

    def update_hoop(self, hoop_dets: list[Detection]):
        """Update hoop position from detections. Use highest confidence."""
        if hoop_dets:
            best = max(hoop_dets, key=lambda d: d.confidence)
            self.hoop_position = best.bbox
            self.hoop_confidence = best.confidence

    def update_ball(self, ball_dets: list[Detection], frame_idx: int) -> BallState | None:
        """Track ball position with Kalman interpolation. Returns current ball state."""
        if ball_dets:
            best = max(ball_dets, key=lambda d: d.confidence)
            cx = (best.bbox[0] + best.bbox[2]) / 2
            cy = (best.bbox[1] + best.bbox[3]) / 2
            return self.ball_tracker.update(cx, cy, frame_idx, best.confidence)
        else:
            # No detection — let Kalman predict
            return self.ball_tracker.update(None, None, frame_idx, 0.0)

    def check_made_basket(self, frame_idx: int) -> float:
        """Check if ball trajectory indicates a made basket.

        Returns confidence (0-1), or 0 if no shot detected.
        """
        if not self.hoop_position:
            return 0.0

        trajectory = self.ball_tracker.get_recent_trajectory(45)
        if len(trajectory) < 3:
            return 0.0

        hx1, hy1, hx2, hy2 = self.hoop_position
        hoop_cx = (hx1 + hx2) / 2
        hoop_cy = (hy1 + hy2) / 2
        hoop_w = hx2 - hx1
        hoop_h = hy2 - hy1

        # --- Method 1: Up→Down trajectory through rim ---
        conf = self._check_trajectory(trajectory, hx1, hy1, hx2, hy2,
                                       hoop_cx, hoop_cy, hoop_w, hoop_h, frame_idx)
        if conf > 0:
            return conf

        # --- Method 2: Proximity burst (ball near hoop center repeatedly) ---
        conf = self._check_proximity_burst(trajectory, hoop_cx, hoop_cy, hoop_w, hoop_h)
        if conf > 0:
            return conf

        # --- Method 3: Downward velocity near hoop ---
        conf = self._check_velocity_spike(trajectory, hoop_cx, hoop_cy, hoop_w, hoop_h)
        if conf > 0:
            return conf

        return 0.0

    def _check_trajectory(self, trajectory: list[BallState],
                          hx1, hy1, hx2, hy2,
                          hoop_cx, hoop_cy, hoop_w, hoop_h,
                          frame_idx: int) -> float:
        """Classic up→down transition check with loosened thresholds."""
        ball = trajectory[-1]
        rim_top = hy1 - hoop_h  # More generous — 1x hoop height above rim (was 0.5x)

        # Check: is ball in the general hoop area horizontally?
        # Use 6x hoop width (was 4x) — gym cameras vary widely
        near_hoop_x = abs(ball.cx - hoop_cx) < 6 * hoop_w

        if not near_hoop_x:
            self._ball_above_hoop = False
            return 0.0

        # Track up→down transition
        if ball.cy < rim_top and not self._ball_above_hoop:
            self._ball_above_hoop = True
            self._above_frame = frame_idx

        if self._ball_above_hoop and ball.cy > hy2:
            # Ball went from above to below hoop
            self._ball_above_hoop = False

            # Don't count if the transition took too long (>2 seconds = not a shot)
            if (frame_idx - self._above_frame) > 60:
                return 0.0

            # This is a shot attempt (ball went up and came down near the hoop)
            self._shot_attempt_pending = True
            self._last_shot_attempt_frame = frame_idx

            # Find positions above and below hoop for interpolation
            above_pos = None
            below_pos = None
            for state in reversed(trajectory):
                if state.cy < hy1 and above_pos is None:
                    above_pos = (state.cx, state.cy)
                if state.cy > hy2 and below_pos is None:
                    below_pos = (state.cx, state.cy)
                if above_pos and below_pos:
                    break

            if above_pos and below_pos and above_pos[1] != below_pos[1]:
                # Interpolate where ball crosses rim height
                t = (hoop_cy - above_pos[1]) / (below_pos[1] - above_pos[1])
                predicted_x = above_pos[0] + t * (below_pos[0] - above_pos[0])

                # Wider rim tolerance (was 0.3x, now 0.5x on each side)
                rim_left = hx1 - 0.5 * hoop_w
                rim_right = hx2 + 0.5 * hoop_w

                if rim_left < predicted_x < rim_right:
                    self._shot_attempt_pending = False  # Will be classified as made
                    return 0.85  # High confidence — trajectory through rim
                else:
                    # Near miss — still could be a make with noisy tracking
                    rim_left_loose = hx1 - 1.0 * hoop_w
                    rim_right_loose = hx2 + 1.0 * hoop_w
                    if rim_left_loose < predicted_x < rim_right_loose:
                        self._shot_attempt_pending = False  # Will be classified as made
                        return 0.55  # Lower confidence — might be a make

        return 0.0

    def _check_proximity_burst(self, trajectory: list[BallState],
                                hoop_cx, hoop_cy, hoop_w, hoop_h) -> float:
        """Detect made basket when ball appears near hoop center multiple times.

        In gym footage, the ball often "appears" inside the hoop bbox for several frames
        when going through the net, even without a clean up→down trajectory.
        """
        recent = trajectory[-20:]  # Last ~0.7 seconds
        if len(recent) < 5:
            return 0.0

        near_count = 0
        for state in recent:
            dx = abs(state.cx - hoop_cx) / max(hoop_w, 1)
            dy = abs(state.cy - hoop_cy) / max(hoop_h, 1)
            if dx < 1.5 and dy < 2.0:  # Within 1.5x hoop width and 2x hoop height
                near_count += 1

        # Need at least 4 frames near hoop in a 20-frame window
        if near_count >= 4:
            # Also check that ball moved downward through this region
            first_near = None
            last_near = None
            for state in recent:
                dx = abs(state.cx - hoop_cx) / max(hoop_w, 1)
                dy = abs(state.cy - hoop_cy) / max(hoop_h, 1)
                if dx < 1.5 and dy < 2.0:
                    if first_near is None:
                        first_near = state
                    last_near = state

            if first_near and last_near and last_near.cy > first_near.cy:
                # Ball moved downward through hoop region
                return 0.65

        return 0.0

    def _check_velocity_spike(self, trajectory: list[BallState],
                               hoop_cx, hoop_cy, hoop_w, hoop_h) -> float:
        """Detect sudden downward velocity near hoop — ball falling through net."""
        if len(trajectory) < 5:
            return 0.0

        recent = trajectory[-8:]
        if len(recent) < 4:
            return 0.0

        # Check if ball is near hoop
        latest = recent[-1]
        dx = abs(latest.cx - hoop_cx)
        if dx > 3 * hoop_w:
            return 0.0

        # Calculate vertical velocity over last few frames
        velocities = []
        for i in range(1, len(recent)):
            dy = recent[i].cy - recent[i - 1].cy
            velocities.append(dy)

        if not velocities:
            return 0.0

        avg_vy = sum(velocities) / len(velocities)
        max_vy = max(velocities)

        # Strong downward velocity near hoop height
        near_hoop_y = abs(latest.cy - hoop_cy) < 3 * hoop_h
        if near_hoop_y and avg_vy > hoop_h * 0.3 and max_vy > hoop_h * 0.5:
            return 0.6

        return 0.0


class EventDetector:
    """Detects made baskets, missed baskets, steals, assists, and rebounds from possession + detection data."""

    STEAL_COOLDOWN_FRAMES = 60  # Don't detect steals within N frames of each other
    ASSIST_WINDOW_FRAMES = 150  # ~5 seconds at 30fps — pass before basket = assist
    BASKET_COOLDOWN_FRAMES = 180  # ~6 seconds between baskets at 30fps
    REBOUND_COOLDOWN_FRAMES = 90  # ~3 seconds between rebounds
    REBOUND_WINDOW_FRAMES = 150  # Look back 5 seconds for a missed shot
    MISS_CONFIRM_FRAMES = 45  # ~1.5s after shot attempt — if no made_basket, it's a miss

    def __init__(self):
        self.shot_tracker = ShotTracker()
        self.possession_history: deque = deque(maxlen=300)  # (frame_idx, PossessionState)
        self._last_steal_frame = -999
        self._last_made_basket_frame = -999
        self._last_rebound_frame = -999
        self._last_missed_basket_frame = -999

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
        if shot_conf > 0.5 and (frame_idx - self._last_made_basket_frame) > self.BASKET_COOLDOWN_FRAMES:
            scorer_id = possession.last_holder_track_id if possession.ball_status == "in_air" else possession.holder_track_id
            if scorer_id >= 0:
                self._last_made_basket_frame = frame_idx
                # Clear any pending shot attempt — it was a make, not a miss
                self.shot_tracker._shot_attempt_pending = False
                events.append(BasketballEvent(
                    event_type="made_basket",
                    frame_idx=frame_idx,
                    timestamp=timestamp,
                    player_track_id=scorer_id,
                    confidence=shot_conf,
                    metadata={"scorer_track_id": scorer_id},
                ))
                logger.info(f"Made basket detected at frame {frame_idx} "
                           f"(t={timestamp:.1f}s, conf={shot_conf:.2f}, scorer=track_{scorer_id})")

                # Check for assist
                assist_event = self._check_assist(frame_idx, timestamp, scorer_id)
                if assist_event:
                    events.append(assist_event)

        # Check for missed basket — shot attempt that wasn't followed by a make
        if (
            self.shot_tracker._shot_attempt_pending
            and (frame_idx - self.shot_tracker._last_shot_attempt_frame) > self.MISS_CONFIRM_FRAMES
            and (frame_idx - self._last_missed_basket_frame) > self.BASKET_COOLDOWN_FRAMES
        ):
            self.shot_tracker._shot_attempt_pending = False
            self._last_missed_basket_frame = frame_idx
            # Attribute to last holder before the shot went up
            shooter_id = possession.last_holder_track_id if possession.last_holder_track_id >= 0 else possession.holder_track_id
            if shooter_id >= 0:
                miss_timestamp = self.shot_tracker._last_shot_attempt_frame / 30.0  # approximate
                # Use the actual timestamp from the attempt frame, not current frame
                # But we don't store it — use current timestamp minus the delay
                delay_seconds = (frame_idx - self.shot_tracker._last_shot_attempt_frame) / 30.0
                events.append(BasketballEvent(
                    event_type="missed_basket",
                    frame_idx=self.shot_tracker._last_shot_attempt_frame,
                    timestamp=timestamp - delay_seconds,
                    player_track_id=shooter_id,
                    confidence=0.5,
                    metadata={"shooter_track_id": shooter_id},
                ))
                logger.info(f"Missed basket detected at frame {self.shot_tracker._last_shot_attempt_frame} "
                           f"(t={timestamp - delay_seconds:.1f}s, shooter=track_{shooter_id})")

        # Check for steal
        steal_event = self._check_steal(frame_idx, timestamp, possession)
        if steal_event:
            events.append(steal_event)

        # Check for rebound (ball in air for extended period, then new holder)
        rebound_event = self._check_rebound(frame_idx, timestamp, possession)
        if rebound_event:
            events.append(rebound_event)

        return events

    def _check_rebound(
        self, frame_idx: int, timestamp: float, possession: PossessionState
    ) -> BasketballEvent | None:
        """Detect rebound: ball was in air for extended time, then someone grabs it.

        A rebound is: ball_status was 'in_air' for 15+ frames in the last 5 seconds,
        and now a player has just gained possession (frames_held crossing MIN_FRAMES threshold).
        """
        if (frame_idx - self._last_rebound_frame) < self.REBOUND_COOLDOWN_FRAMES:
            return None

        # Need a holder who just confirmed possession
        if possession.holder_track_id < 0 or possession.frames_held != 1:
            return None

        # Count recent air frames in the last 5 seconds
        recent_air_frames = 0
        for hist_frame, ps in reversed(self.possession_history):
            if frame_idx - hist_frame > self.REBOUND_WINDOW_FRAMES:
                break
            if ps.ball_status == "in_air":
                recent_air_frames += 1

        # Need 15+ air frames (~0.5s of ball in air) — indicates a missed shot or loose ball
        if recent_air_frames >= 15:
            # Don't log as rebound if we just logged a made basket (ball goes through net = in_air)
            if (frame_idx - self._last_made_basket_frame) < 90:
                return None

            self._last_rebound_frame = frame_idx
            rebounder_id = possession.holder_track_id
            logger.info(f"Rebound detected at frame {frame_idx} "
                       f"(t={timestamp:.1f}s, rebounder=track_{rebounder_id})")
            return BasketballEvent(
                event_type="rebound",
                frame_idx=frame_idx,
                timestamp=timestamp,
                player_track_id=rebounder_id,
                confidence=0.6,
                metadata={
                    "rebounder_track_id": rebounder_id,
                    "air_frames": recent_air_frames,
                },
            )
        return None

    def _check_steal(
        self, frame_idx: int, timestamp: float, possession: PossessionState
    ) -> BasketballEvent | None:
        """Detect steal: possession changes teams without a shot attempt.

        When team classification is available, requires cross-team change.
        When teams are unknown (both None), falls back to heuristic:
        different player, brief air time (1-5 frames), and distance check.
        """
        if (frame_idx - self._last_steal_frame) < self.STEAL_COOLDOWN_FRAMES:
            return None

        if (
            possession.holder_track_id >= 0
            and possession.last_holder_track_id >= 0
            and possession.holder_track_id != possession.last_holder_track_id
            and possession.frames_held <= 3  # Recently changed (within confirmation window)
        ):
            has_team_info = (possession.holder_team is not None
                            and possession.last_holder_team is not None)

            if has_team_info and possession.holder_team != possession.last_holder_team:
                # Team-based steal detection (original logic)
                recent_air_frames = sum(
                    1 for _, ps in self.possession_history
                    if ps.ball_status == "in_air"
                    and frame_idx - _ < 30  # last second
                )
                if recent_air_frames < 15:
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

            elif not has_team_info:
                # Teamless fallback: detect "possible steal" based on heuristics
                # 1. Ball was briefly in_air or not_visible (1-5 frames)
                recent_air_frames = sum(
                    1 for _, ps in self.possession_history
                    if ps.ball_status in ("in_air", "not_visible")
                    and frame_idx - _ < 30
                )
                if 1 <= recent_air_frames <= 15:
                    # 2. Check distance between holder and last holder bboxes
                    # (uses possession history to find their positions)
                    holder_bbox = self._find_player_bbox_in_history(
                        frame_idx, possession.holder_track_id)
                    victim_bbox = self._find_player_bbox_in_history(
                        frame_idx, possession.last_holder_track_id)
                    # If we can't find bboxes, still allow with lower confidence
                    far_enough = True
                    if holder_bbox and victim_bbox:
                        hcx = (holder_bbox[0] + holder_bbox[2]) / 2
                        hcy = (holder_bbox[1] + holder_bbox[3]) / 2
                        vcx = (victim_bbox[0] + victim_bbox[2]) / 2
                        vcy = (victim_bbox[1] + victim_bbox[3]) / 2
                        dist = math.sqrt((hcx - vcx) ** 2 + (hcy - vcy) ** 2)
                        # Players should be relatively close for a steal (within 300px)
                        far_enough = dist < 300

                    if far_enough:
                        self._last_steal_frame = frame_idx
                        logger.info(f"Possible steal (teamless) at frame {frame_idx} "
                                   f"(t={timestamp:.1f}s, stealer=track_{possession.holder_track_id}, "
                                   f"victim=track_{possession.last_holder_track_id})")
                        return BasketballEvent(
                            event_type="steal",
                            frame_idx=frame_idx,
                            timestamp=timestamp,
                            player_track_id=possession.holder_track_id,
                            confidence=0.5,
                            metadata={
                                "stealer_track_id": possession.holder_track_id,
                                "victim_track_id": possession.last_holder_track_id,
                                "detection_mode": "teamless_heuristic",
                            },
                        )
        return None

    def _find_player_bbox_in_history(
        self, frame_idx: int, track_id: int
    ) -> tuple[float, float, float, float] | None:
        """Search recent detection history for a player's bbox. Returns None if not found."""
        # EventDetector doesn't store raw detections, so this is a best-effort lookup
        # via possession history metadata. Returns None (caller handles gracefully).
        return None

    def _check_assist(
        self, frame_idx: int, timestamp: float, scorer_track_id: int
    ) -> BasketballEvent | None:
        """Check if there was a same-team pass leading to this made basket.

        Looks back through possession history for a different same-team player
        who held the ball before the scorer, allowing for brief 'in_air' gaps
        between pass and reception.

        When team info is unavailable, falls back to: any different player who
        held the ball within 3 seconds before the basket (lower confidence).
        """
        scorer_team = None
        prev_holder = None
        seen_scorer = False
        has_any_team_info = False
        # Teamless fallback: track the most recent different holder within 3s
        teamless_prev_holder = None
        teamless_holder_frame = -1

        for hist_frame, ps in reversed(self.possession_history):
            if frame_idx - hist_frame > self.ASSIST_WINDOW_FRAMES:
                break

            # Track whether any team info exists in the history
            if ps.holder_team is not None or ps.last_holder_team is not None:
                has_any_team_info = True

            # Identify the scorer's team
            if ps.holder_track_id == scorer_track_id and scorer_team is None:
                scorer_team = ps.holder_team
                seen_scorer = True

            # Also check last_holder — the passer might show up there during 'in_air' phase
            if scorer_team is None and ps.last_holder_track_id == scorer_track_id:
                scorer_team = ps.last_holder_team
                seen_scorer = True

            # Found a different player on the same team who had the ball
            if (
                seen_scorer
                and scorer_team
                and ps.holder_track_id != scorer_track_id
                and ps.holder_track_id >= 0
                and ps.holder_team == scorer_team
            ):
                prev_holder = ps.holder_track_id
                break

            # Also check last_holder for the passer
            if (
                seen_scorer
                and scorer_team
                and ps.last_holder_track_id != scorer_track_id
                and ps.last_holder_track_id >= 0
                and ps.last_holder_team == scorer_team
            ):
                prev_holder = ps.last_holder_track_id
                break

            # Teamless fallback: track the most recent different holder within 3s (90 frames)
            if (
                seen_scorer
                and teamless_prev_holder is None
                and frame_idx - hist_frame <= 90  # 3 seconds
                and ps.holder_track_id != scorer_track_id
                and ps.holder_track_id >= 0
            ):
                teamless_prev_holder = ps.holder_track_id
                teamless_holder_frame = hist_frame

        if prev_holder is not None and prev_holder != scorer_track_id:
            logger.info(f"Assist detected at frame {frame_idx} "
                       f"(t={timestamp:.1f}s, assister=track_{prev_holder}, scorer=track_{scorer_track_id})")
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

        # Teamless fallback: no team info available, use proximity-in-time heuristic
        if (
            prev_holder is None
            and not has_any_team_info
            and teamless_prev_holder is not None
            and teamless_prev_holder != scorer_track_id
        ):
            logger.info(f"Possible assist (teamless) at frame {frame_idx} "
                       f"(t={timestamp:.1f}s, assister=track_{teamless_prev_holder}, "
                       f"scorer=track_{scorer_track_id})")
            return BasketballEvent(
                event_type="assist",
                frame_idx=frame_idx,
                timestamp=timestamp,
                player_track_id=teamless_prev_holder,
                confidence=0.4,
                metadata={
                    "assister_track_id": teamless_prev_holder,
                    "scorer_track_id": scorer_track_id,
                    "detection_mode": "teamless_heuristic",
                },
            )
        return None

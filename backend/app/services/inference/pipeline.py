"""
Main inference pipeline — orchestrates detection, tracking, ReID, classification, OCR, and event detection.
"""

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.services.inference.detector import PlayerBallDetector, Detection
from app.services.inference.team_classifier import TeamClassifier
from app.services.inference.ocr import JerseyOCR
from app.services.inference.court_mapper import CourtMapper
from app.services.inference.reid import ReIDExtractor, ReIDMatcher, ReIDMatch

logger = logging.getLogger(__name__)


@dataclass
class GameEvent:
    event_type: str  # possession, made_shot, turnover, etc.
    frame_idx: int
    timestamp: float  # seconds
    player_track_id: int | None = None
    team: str | None = None
    court_x: float | None = None
    court_y: float | None = None
    jersey_number: int | None = None
    player_name: str | None = None


@dataclass
class PlayerInfo:
    track_id: int
    team_idx: int | None = None
    team_name: str | None = None
    jersey_number: int | None = None
    player_name: str | None = None
    roster_player_id: str | None = None  # matched roster player UUID
    reid_confidence: float = 0.0
    jersey_votes: dict[int, int] = field(default_factory=dict)
    team_votes: dict[int, int] = field(default_factory=dict)
    reid_votes: dict[str, int] = field(default_factory=dict)  # roster_player_id -> vote count
    is_roster_matched: bool = False


class InferencePipeline:
    def __init__(
        self,
        team_descriptions: list[str],
        team_names: list[str],
        model_path: str = "yolov8x.pt",
        calibration_path: str | None = None,
        roster_players: list[dict] | None = None,
    ):
        self.detector = PlayerBallDetector(model_path)
        self.classifier = TeamClassifier()
        self.ocr = JerseyOCR()
        self.court_mapper = CourtMapper()

        # ReID components
        self.reid_extractor = ReIDExtractor()
        self.reid_matcher = ReIDMatcher()

        self.team_descriptions = team_descriptions
        self.team_names = team_names

        if calibration_path:
            self.court_mapper.load_calibration(calibration_path)

        # Load roster embeddings if provided
        if roster_players:
            self.reid_matcher.load_roster(roster_players)

        self.players: dict[int, PlayerInfo] = {}
        self.events: list[GameEvent] = []
        self._fps: float = 30.0

    def _get_player_crop(self, frame: np.ndarray, det: Detection) -> np.ndarray:
        x1, y1, x2, y2 = [int(v) for v in det.bbox]
        return frame[y1:y2, x1:x2]

    def _try_reid_match(self, crop: np.ndarray, player: PlayerInfo):
        """Attempt to match a player crop to a roster player via ReID."""
        embedding = self.reid_extractor.extract_embedding(crop)
        match = self.reid_matcher.match(embedding)

        if match is None:
            return

        # Vote for this roster player
        player.reid_votes[match.player_id] = player.reid_votes.get(match.player_id, 0) + 1

        # Need consistent votes before confirming match
        best_id = max(player.reid_votes, key=player.reid_votes.get)
        vote_count = player.reid_votes[best_id]

        if vote_count >= 3 and not player.is_roster_matched:
            # Confirmed match — override team/jersey from roster data
            player.roster_player_id = match.player_id
            player.player_name = match.name
            player.jersey_number = match.jersey_number
            player.reid_confidence = match.confidence
            player.is_roster_matched = True

            # Set team from roster
            for idx, name in enumerate(self.team_names):
                if name == match.team_name:
                    player.team_idx = idx
                    player.team_name = name
                    break

            logger.debug(f"Track {player.track_id} matched to {match.name} "
                        f"(#{match.jersey_number}) confidence={match.confidence:.2f}")

    def _update_player_info(self, det: Detection, frame: np.ndarray):
        if det.track_id < 0 or det.class_name != "person":
            return

        if det.track_id not in self.players:
            self.players[det.track_id] = PlayerInfo(track_id=det.track_id)

        player = self.players[det.track_id]
        crop = self._get_player_crop(frame, det)

        if crop.size == 0:
            return

        # ReID matching (every 15 frames until matched)
        if not player.is_roster_matched and det.frame_idx % 15 == 0:
            self._try_reid_match(crop, player)

        # Skip CLIP/OCR if already matched via ReID — we already know who they are
        if player.is_roster_matched:
            return

        # Fallback: Team classification via CLIP (every 30 frames)
        if det.frame_idx % 30 == 0:
            team_idx, conf = self.classifier.classify(crop, self.team_descriptions)
            if conf > 0.6:
                player.team_votes[team_idx] = player.team_votes.get(team_idx, 0) + 1
                best_team = max(player.team_votes, key=player.team_votes.get)
                player.team_idx = best_team
                player.team_name = self.team_names[best_team]

        # Fallback: Jersey OCR (every 60 frames)
        if det.frame_idx % 60 == 0 and player.jersey_number is None:
            number = self.ocr.read_number(crop)
            if number is not None:
                player.jersey_votes[number] = player.jersey_votes.get(number, 0) + 1
                if player.jersey_votes[number] >= 3:
                    player.jersey_number = number

    def _detect_events(self, frame_idx: int, timestamp: float, detections: list[Detection]):
        """MVP event detection: create possession markers at intervals."""
        # Every ~5 seconds, create a possession event
        interval_frames = int(5 * self._fps)
        if interval_frames <= 0:
            interval_frames = 150

        if frame_idx == 0 or frame_idx % interval_frames != 0:
            return

        # Find ball and person detections
        ball_dets = [d for d in detections if d.class_name == "ball"]
        person_dets = [d for d in detections if d.class_name == "person" and d.track_id >= 0]

        if not person_dets:
            return

        # Find the player nearest to the ball (if ball detected)
        nearest_track_id = None
        if ball_dets:
            ball = ball_dets[0]
            ball_cx = (ball.bbox[0] + ball.bbox[2]) / 2
            ball_cy = (ball.bbox[1] + ball.bbox[3]) / 2

            best_dist = float("inf")
            for det in person_dets:
                px = (det.bbox[0] + det.bbox[2]) / 2
                py = (det.bbox[1] + det.bbox[3]) / 2
                dist = ((px - ball_cx) ** 2 + (py - ball_cy) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    nearest_track_id = det.track_id
        else:
            # No ball detected — pick a random tracked person
            nearest_track_id = person_dets[0].track_id

        player_info = self.players.get(nearest_track_id)

        self.events.append(GameEvent(
            event_type="possession",
            frame_idx=frame_idx,
            timestamp=timestamp,
            player_track_id=nearest_track_id,
            team=player_info.team_name if player_info else None,
            jersey_number=player_info.jersey_number if player_info else None,
            player_name=player_info.player_name if player_info else None,
        ))

    def process(self, video_path: str) -> list[GameEvent]:
        """Run the full inference pipeline on a video."""
        cap = cv2.VideoCapture(video_path)
        self._fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        logger.info(f"Processing video: {video_path} at {self._fps} FPS, {total_frames} frames")
        logger.info(f"Roster players loaded: {len(self.reid_matcher.roster_embeddings)}")

        # Open a parallel reader for frame crops — stays in sync with YOLO stream
        frame_reader = cv2.VideoCapture(video_path)

        for frame_idx, detections in self.detector.process_video(video_path):
            timestamp = frame_idx / self._fps if self._fps > 0 else 0

            ret, frame = frame_reader.read()
            if not ret:
                break

            for det in detections:
                self._update_player_info(det, frame)

            self._detect_events(frame_idx, timestamp, detections)

            # Log progress every 1000 frames
            if frame_idx > 0 and frame_idx % 1000 == 0:
                pct = (frame_idx / total_frames * 100) if total_frames > 0 else 0
                logger.info(f"Frame {frame_idx}/{total_frames} ({pct:.1f}%) — "
                           f"{len(self.events)} events, {len(self.players)} players")

        frame_reader.release()

        # Summary
        matched = sum(1 for p in self.players.values() if p.is_roster_matched)
        logger.info(f"Pipeline complete. {len(self.events)} events detected, "
                    f"{len(self.players)} players tracked, {matched} matched to roster")

        return self.events

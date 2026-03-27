"""
Main inference pipeline — orchestrates detection, tracking, ReID, possession, and event detection.
Player-centric: processes video for a specific target profile, filtering events to that player.
"""

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.services.inference.detector import PlayerBallDetector, Detection
from app.services.inference.event_detector import BasketballEvent, EventDetector
from app.services.inference.ocr import JerseyOCR
from app.services.inference.possession_tracker import PossessionTracker
from app.services.inference.reid import ReIDExtractor, ReIDMatcher
from app.services.inference.team_classifier import TeamClassifier

logger = logging.getLogger(__name__)


@dataclass
class PlayerInfo:
    track_id: int
    team_name: str | None = None
    jersey_number: int | None = None
    reid_confidence: float = 0.0
    team_votes: dict[int, int] = field(default_factory=dict)
    jersey_votes: dict[int, int] = field(default_factory=dict)
    reid_votes: dict[str, int] = field(default_factory=dict)
    is_target: bool = False  # matched to target profile


class InferencePipeline:
    def __init__(
        self,
        model_path: str = "yolov8x.pt",
        hoop_model_path: str | None = None,
        profile_embeddings: list[np.ndarray] | None = None,
        team_descriptions: list[str] | None = None,
        team_names: list[str] | None = None,
    ):
        self.detector = PlayerBallDetector(model_path, hoop_model_path=hoop_model_path)
        self.possession_tracker = PossessionTracker()
        self.event_detector = EventDetector()
        self.reid_extractor = ReIDExtractor()
        self.reid_matcher = ReIDMatcher()
        self.ocr = JerseyOCR()

        # Optional CLIP classifier for team assignment
        self.classifier = None
        self.team_descriptions = team_descriptions or []
        self.team_names = team_names or []
        if self.team_descriptions:
            self.classifier = TeamClassifier()

        # Load target profile embeddings
        if profile_embeddings:
            self.reid_matcher.load_profile(profile_embeddings)

        self.players: dict[int, PlayerInfo] = {}
        self.target_track_ids: set[int] = set()
        self._fps: float = 30.0

    def _get_player_crop(self, frame: np.ndarray, det: Detection) -> np.ndarray:
        x1, y1, x2, y2 = [int(v) for v in det.bbox]
        return frame[y1:y2, x1:x2]

    def _update_player_info(self, det: Detection, frame: np.ndarray):
        if det.track_id < 0 or det.class_name != "person":
            return

        if det.track_id not in self.players:
            self.players[det.track_id] = PlayerInfo(track_id=det.track_id)

        player = self.players[det.track_id]
        crop = self._get_player_crop(frame, det)

        if crop.size == 0:
            return

        # ReID matching to target profile (every 15 frames until matched)
        if not player.is_target and det.frame_idx % 15 == 0:
            embedding = self.reid_extractor.extract_embedding(crop)
            match = self.reid_matcher.match(embedding)
            if match:
                player.reid_votes["target"] = player.reid_votes.get("target", 0) + 1
                if player.reid_votes["target"] >= 3:
                    player.is_target = True
                    player.reid_confidence = match.confidence
                    self.target_track_ids.add(det.track_id)
                    logger.info(f"Track {det.track_id} matched to target profile "
                               f"(confidence={match.confidence:.2f})")

        # Team classification via CLIP (every 30 frames, if configured)
        if self.classifier and det.frame_idx % 30 == 0 and player.team_name is None:
            team_idx, conf = self.classifier.classify(crop, self.team_descriptions)
            if conf > 0.6:
                player.team_votes[team_idx] = player.team_votes.get(team_idx, 0) + 1
                best_team = max(player.team_votes, key=player.team_votes.get)
                player.team_name = self.team_names[best_team]

        # Jersey OCR (every 60 frames)
        if det.frame_idx % 60 == 0 and player.jersey_number is None:
            number = self.ocr.read_number(crop)
            if number is not None:
                player.jersey_votes[number] = player.jersey_votes.get(number, 0) + 1
                if player.jersey_votes[number] >= 3:
                    player.jersey_number = number

    def process(self, video_path: str, target_fps: int = 30) -> list[BasketballEvent]:
        """Run the full inference pipeline on a video.

        Returns events filtered to the target profile's matched track IDs.
        """
        cap = cv2.VideoCapture(video_path)
        self._fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        vid_stride = max(1, round(self._fps / target_fps))
        effective_fps = self._fps / vid_stride
        total_processed = total_frames // vid_stride

        logger.info(f"Processing video: {video_path} at {self._fps} FPS, {total_frames} frames")
        logger.info(f"vid_stride={vid_stride}, effective FPS={effective_fps:.1f}, ~{total_processed} frames to process")

        all_events: list[BasketballEvent] = []

        for frame_idx, detections, frame in self.detector.process_video(video_path, vid_stride=vid_stride):
            actual_frame = frame_idx * vid_stride
            timestamp = actual_frame / self._fps if self._fps > 0 else 0

            if frame is None:
                continue

            # Update player info (ReID, team, jersey)
            for det in detections:
                self._update_player_info(det, frame)

            # Build team mapping for possession tracker
            player_teams = {
                tid: p.team_name for tid, p in self.players.items() if p.team_name
            }

            # Update possession
            possession = self.possession_tracker.update(detections, player_teams)

            # Detect events
            events = self.event_detector.update(frame_idx, timestamp, detections, possession)
            all_events.extend(events)

            # Log progress every 1000 processed frames
            if frame_idx > 0 and frame_idx % 1000 == 0:
                pct = (frame_idx / total_processed * 100) if total_processed > 0 else 0
                logger.info(f"Frame {frame_idx}/{total_processed} ({pct:.1f}%) — "
                           f"{len(all_events)} events, {len(self.players)} players, "
                           f"{len(self.target_track_ids)} target tracks")

        # Filter events to target profile's track IDs
        if self.target_track_ids:
            filtered = [e for e in all_events if e.player_track_id in self.target_track_ids]
            logger.info(f"Pipeline complete. {len(all_events)} total events, "
                       f"{len(filtered)} for target profile, "
                       f"{len(self.players)} players tracked, "
                       f"{len(self.target_track_ids)} target tracks matched")
            return filtered
        else:
            logger.warning("No target tracks matched — returning all events")
            return all_events

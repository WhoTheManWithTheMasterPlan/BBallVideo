"""
Main inference pipeline — orchestrates detection, tracking, ReID, possession, and event detection.
Player-centric: processes video for a specific target profile, filtering events to that player.

Uses dual made-basket detection:
  1. Heuristic (ball trajectory through hoop via Kalman tracking)
  2. ResNet50 scoring classifier (visual classification of hoop crop)
Both signals are merged with deduplication.

Action classification: MViT v2-S classifies 16-frame player crops into 10 basketball actions.
"""

import logging
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.services.inference.detector import PlayerBallDetector, Detection
from app.services.inference.event_detector import BasketballEvent, EventDetector
from app.services.inference.ocr import JerseyOCR
from app.services.inference.pose_estimator import PoseEstimator
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
    last_pose: str | None = None  # last classified pose: "shooting", "dribbling", "other"
    last_pose_confidence: float = 0.0
    last_action: str | None = None  # MViT v2-S action: "shoot", "dribble", "pass", etc.
    last_action_confidence: float = 0.0


class InferencePipeline:
    def __init__(
        self,
        model_path: str = "yolov8x.pt",
        hoop_model_path: str | None = None,
        profile_embeddings: list[np.ndarray] | None = None,
        profile_jersey_number: int | None = None,
        team_descriptions: list[str] | None = None,
        team_names: list[str] | None = None,
    ):
        self.detector = PlayerBallDetector(model_path, hoop_model_path=hoop_model_path)
        self.possession_tracker = PossessionTracker()
        self.event_detector = EventDetector()
        self.reid_extractor = ReIDExtractor()
        self.reid_matcher = ReIDMatcher()
        self.ocr = JerseyOCR()

        # Pose estimator (yolov8m-pose — medium model to conserve VRAM)
        self.pose_estimator: PoseEstimator | None = None
        try:
            self.pose_estimator = PoseEstimator()
            logger.info("Pose estimator enabled")
        except Exception as e:
            logger.warning(f"Pose estimator not available: {e}")

        # Scoring classifier (ResNet50 hoop crop classifier)
        self.scoring_classifier = None
        try:
            from app.services.inference.scoring_classifier import ScoringClassifier
            self.scoring_classifier = ScoringClassifier()
            logger.info("Scoring classifier enabled")
        except Exception as e:
            logger.warning(f"Scoring classifier not available: {e}")

        # Action classifier (MViT v2-S — 10 basketball action classes)
        self.action_classifier = None
        try:
            from app.services.inference.action_classifier import ActionClassifier
            self.action_classifier = ActionClassifier()
            logger.info("Action classifier enabled")
        except Exception as e:
            logger.warning(f"Action classifier not available: {e}")

        # Per-player frame crop buffers for action classification (16-frame sliding window)
        self._player_crop_buffers: dict[int, deque] = {}

        # Court detector (YOLOv8-pose — court keypoint detection for shot chart)
        self.court_detector = None
        try:
            from app.services.inference.court_detector import CourtDetector
            self.court_detector = CourtDetector()
            logger.info("Court detector enabled")
        except Exception as e:
            logger.warning(f"Court detector not available: {e}")

        # Profile jersey number — used to boost/confirm ReID matches
        self.profile_jersey_number = profile_jersey_number

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
        # Skip ReID for players classified as opponents (team color pre-filter)
        if not player.is_target and det.frame_idx % 15 == 0:
            # TODO: Add jersey color selection at upload time so CLIP can pre-filter opponents
            # For now, skip CLIP team filtering — rely on ReID threshold + jersey OCR only
            embedding = self.reid_extractor.extract_embedding(crop)
            match = self.reid_matcher.match(embedding)
            if match:
                player.reid_votes["target"] = player.reid_votes.get("target", 0) + 1
                votes_needed = 3

                # Jersey number match lowers the confirmation threshold
                if (self.profile_jersey_number is not None
                        and player.jersey_number == self.profile_jersey_number):
                    votes_needed = 1  # Instant confirm: ReID + jersey match

                if player.reid_votes["target"] >= votes_needed:
                    player.is_target = True
                    player.reid_confidence = match.confidence
                    self.target_track_ids.add(det.track_id)
                    logger.info(f"Track {det.track_id} matched to target profile "
                               f"(confidence={match.confidence:.2f}, "
                               f"jersey={'match' if player.jersey_number == self.profile_jersey_number else 'n/a'})")

        # Jersey number match alone (no ReID needed if jersey is confirmed)
        if (not player.is_target
                and self.profile_jersey_number is not None
                and player.jersey_number == self.profile_jersey_number
                and player.jersey_votes.get(self.profile_jersey_number, 0) >= 5):
            # Strong jersey OCR evidence (5+ reads) — accept as target even without ReID
            player.is_target = True
            player.reid_confidence = 0.5  # Lower confidence for jersey-only match
            self.target_track_ids.add(det.track_id)
            logger.info(f"Track {det.track_id} matched to target by jersey #{self.profile_jersey_number} "
                       f"(OCR-only, {player.jersey_votes[self.profile_jersey_number]} reads)")

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
        Uses dual detection: heuristic (trajectory) + classifier (ResNet50 hoop crop).
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

        heuristic_events: list[BasketballEvent] = []
        # Track hoop bbox for scoring classifier
        last_hoop_bbox: tuple[float, float, float, float] | None = None
        # Current homography matrix for court mapping
        current_H: np.ndarray | None = None
        # Store homography + player bboxes per frame for post-loop classifier event enrichment
        frame_homographies: dict[int, np.ndarray] = {}  # frame_idx -> H
        frame_player_bboxes: dict[int, dict[int, tuple]] = {}  # frame_idx -> {track_id -> bbox}
        # Full target possession history (unlike deque, this persists across entire video)
        # Stores (frame_idx, holder_track_id, last_holder_track_id) for every frame
        self._target_possession_log: list[tuple[int, int, int]] = []

        for frame_idx, detections, frame in self.detector.process_video(video_path, vid_stride=vid_stride):
            actual_frame = frame_idx * vid_stride
            timestamp = actual_frame / self._fps if self._fps > 0 else 0

            if frame is None:
                if self.scoring_classifier:
                    self.scoring_classifier.classify_frame(
                        np.zeros((128, 128, 3), dtype=np.uint8), None)
                continue

            # Update player info (ReID, team, jersey)
            for det in detections:
                self._update_player_info(det, frame)

            # Track hoop position for classifier
            hoop_dets = [d for d in detections if d.class_name == "hoop"]
            if hoop_dets:
                best_hoop = max(hoop_dets, key=lambda d: d.confidence)
                last_hoop_bbox = best_hoop.bbox

            # Run scoring classifier on hoop crop (BGR→RGB)
            if self.scoring_classifier:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.scoring_classifier.classify_frame(frame_rgb, last_hoop_bbox)

            # Build team mapping for possession tracker
            player_teams = {
                tid: p.team_name for tid, p in self.players.items() if p.team_name
            }

            # Update possession
            possession = self.possession_tracker.update(detections, player_teams)

            # Log possession for target filtering (every 10 frames to save memory)
            if frame_idx % 10 == 0:
                holder = possession.holder_track_id if possession else -1
                last_holder = possession.last_holder_track_id if possession else -1
                self._target_possession_log.append((frame_idx, holder, last_holder))

            # Pose estimation (every 10 frames to conserve GPU — not every frame)
            if self.pose_estimator and frame_idx % 10 == 0:
                # Run pose model once per frame, then match results to tracked players by IoU
                all_poses = self.pose_estimator.estimate(frame)
                if all_poses:
                    person_dets = [d for d in detections if d.class_name == "person" and d.track_id >= 0]
                    for det in person_dets:
                        best_pose = None
                        best_iou = 0.0
                        for pose in all_poses:
                            iou = self.pose_estimator._compute_iou(pose.bbox, det.bbox)
                            if iou > best_iou and iou >= 0.3:
                                best_iou = iou
                                best_pose = pose
                        if best_pose and det.track_id in self.players:
                            self.players[det.track_id].last_pose = best_pose.action
                            self.players[det.track_id].last_pose_confidence = best_pose.action_confidence

            # Court keypoint detection (every 30 frames for homography)
            if self.court_detector and frame_idx % 30 == 0:
                try:
                    keypoints = self.court_detector.detect_keypoints(frame)
                    if keypoints is not None:
                        H = self.court_detector.compute_homography(keypoints)
                        if H is not None:
                            current_H = H
                except Exception:
                    pass  # Don't break pipeline on court detection errors

            # Store homography + player bboxes for post-loop enrichment (every 30 frames)
            if current_H is not None and frame_idx % 30 == 0:
                frame_homographies[frame_idx] = current_H.copy()
            person_dets_all = [d for d in detections if d.class_name == "person" and d.track_id >= 0]
            if person_dets_all:
                frame_player_bboxes[frame_idx] = {d.track_id: d.bbox for d in person_dets_all}

            # Action classification (MViT v2-S, every 16 frames per player)
            if self.action_classifier:
                person_dets = [d for d in detections if d.class_name == "person" and d.track_id >= 0]
                for det in person_dets:
                    tid = det.track_id
                    if tid not in self._player_crop_buffers:
                        self._player_crop_buffers[tid] = deque(maxlen=16)
                    crop = self._get_player_crop(frame, det)
                    if crop.size > 0 and crop.shape[0] > 10 and crop.shape[1] > 10:
                        # Store RGB crop for action classifier
                        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                        self._player_crop_buffers[tid].append(crop_rgb)

                    # Classify when buffer is full (every 16 frames of this player)
                    if len(self._player_crop_buffers.get(tid, [])) == 16 and tid in self.players:
                        try:
                            action, conf = self.action_classifier.classify(
                                list(self._player_crop_buffers[tid])
                            )
                            self.players[tid].last_action = action
                            self.players[tid].last_action_confidence = conf
                            self._player_crop_buffers[tid].clear()
                        except Exception:
                            pass  # Don't break pipeline on classifier errors

            # Heuristic event detection (trajectory + Kalman)
            events = self.event_detector.update(frame_idx, timestamp, detections, possession)

            # Enrich events with pose + action + court data from the player involved
            for event in events:
                if event.player_track_id in self.players:
                    player = self.players[event.player_track_id]
                    if player.last_pose:
                        event.metadata["pose"] = player.last_pose
                        event.metadata["pose_confidence"] = player.last_pose_confidence
                    if player.last_action:
                        event.metadata["action"] = player.last_action
                        event.metadata["action_confidence"] = player.last_action_confidence

                # Map event location to court coordinates via homography
                if current_H is not None and self.court_detector and event.player_track_id >= 0:
                    # Find the player's bbox at this frame
                    player_det = next(
                        (d for d in detections
                         if d.track_id == event.player_track_id and d.class_name == "person"),
                        None,
                    )
                    if player_det:
                        foot_x, foot_y = self.court_detector.get_foot_position(player_det.bbox)
                        court_pos = self.court_detector.pixel_to_court(current_H, foot_x, foot_y)
                        if court_pos:
                            event.metadata["court_x"] = court_pos[0]
                            event.metadata["court_y"] = court_pos[1]

            heuristic_events.extend(events)

            # Log progress every 1000 processed frames
            # TODO: Push progress (pct, events count) to ProcessingJob.progress field
            # so frontend can poll /api/v1/jobs/{id} and show a real progress bar
            # instead of just "processing". Update via Celery task self.update_state()
            # or direct DB write from pipeline callback.
            if frame_idx > 0 and frame_idx % 1000 == 0:
                pct = (frame_idx / total_processed * 100) if total_processed > 0 else 0
                logger.info(f"Frame {frame_idx}/{total_processed} ({pct:.1f}%) — "
                           f"{len(heuristic_events)} heuristic events, "
                           f"{len(self.players)} players, "
                           f"{len(self.target_track_ids)} target tracks")

        # Get classifier-based scoring events
        classifier_events: list[BasketballEvent] = []
        if self.scoring_classifier:
            scoring_peaks = self.scoring_classifier.get_scoring_events(
                fps=effective_fps,
                confidence_threshold=0.7,
                min_distance_seconds=6.0,
            )
            for peak in scoring_peaks:
                # Find the closest possession holder at the time of the basket
                scorer_id = self._find_scorer_at_frame(peak["frame_idx"])
                metadata = {"source": "classifier", "scorer_track_id": scorer_id}

                # Enrich with action data from player cache
                if scorer_id in self.players:
                    player = self.players[scorer_id]
                    if player.last_action:
                        metadata["action"] = player.last_action
                        metadata["action_confidence"] = player.last_action_confidence
                    if player.last_pose:
                        metadata["pose"] = player.last_pose
                        metadata["pose_confidence"] = player.last_pose_confidence

                # Enrich with court coordinates from stored homographies
                if self.court_detector and scorer_id >= 0:
                    # Find nearest stored homography
                    best_h_frame = None
                    best_h_dist = float("inf")
                    for h_frame in frame_homographies:
                        dist = abs(h_frame - peak["frame_idx"])
                        if dist < best_h_dist:
                            best_h_dist = dist
                            best_h_frame = h_frame
                    if best_h_frame is not None and best_h_dist < 60:  # Within ~2s
                        H = frame_homographies[best_h_frame]
                        # Find nearest stored bbox for this scorer
                        best_bbox_frame = None
                        best_bbox_dist = float("inf")
                        for b_frame in frame_player_bboxes:
                            if scorer_id in frame_player_bboxes[b_frame]:
                                dist = abs(b_frame - peak["frame_idx"])
                                if dist < best_bbox_dist:
                                    best_bbox_dist = dist
                                    best_bbox_frame = b_frame
                        if best_bbox_frame is not None and best_bbox_dist < 60:
                            bbox = frame_player_bboxes[best_bbox_frame][scorer_id]
                            foot_x, foot_y = self.court_detector.get_foot_position(bbox)
                            court_pos = self.court_detector.pixel_to_court(H, foot_x, foot_y)
                            if court_pos:
                                metadata["court_x"] = court_pos[0]
                                metadata["court_y"] = court_pos[1]

                classifier_events.append(BasketballEvent(
                    event_type="made_basket",
                    frame_idx=peak["frame_idx"],
                    timestamp=peak["timestamp"],
                    player_track_id=scorer_id,
                    confidence=peak["confidence"],
                    metadata=metadata,
                ))

        # Merge heuristic + classifier events (deduplicate within 6 seconds)
        all_events = self._merge_events(heuristic_events, classifier_events, gap_seconds=6.0)

        logger.info(f"Pipeline complete: {len(heuristic_events)} heuristic events, "
                   f"{len(classifier_events)} classifier events, "
                   f"{len(all_events)} merged events")

        # Filter events to target profile's track IDs
        if self.target_track_ids:
            filtered = []
            for e in all_events:
                if e.player_track_id in self.target_track_ids:
                    filtered.append(e)
                elif e.event_type == "made_basket":
                    # For baskets, scorer attribution may be wrong — check if any target
                    # track had possession within ±5 seconds of this event
                    target_scorer = self._find_target_near_event(e.frame_idx, window=150)
                    if target_scorer is not None:
                        e.player_track_id = target_scorer
                        e.metadata["scorer_reassigned"] = True
                        filtered.append(e)
                        logger.info(f"Reassigned made_basket at {e.timestamp:.1f}s to target track {target_scorer}")
            logger.info(f"Filtered to target: {len(filtered)} of {len(all_events)} events, "
                       f"{len(self.target_track_ids)} target tracks")
            return filtered
        else:
            # No target matched — return empty instead of all events to avoid wrong-player highlights.
            # The job status will show 0 highlights, signaling that ReID failed.
            logger.warning("No target tracks matched — returning empty (ReID failed to identify target player). "
                          "Check: are profile/team photos uploaded? Are embeddings valid?")
            return []

    def _find_target_near_event(self, frame_idx: int, window: int = 150) -> int | None:
        """Check if any target track had possession within ±window frames of an event.

        Returns the target track_id if found, else None.
        Used to rescue made_basket events where the scorer was misattributed.
        Uses the persistent possession log (not the limited deque).
        """
        best_track = None
        best_dist = float("inf")
        for hist_frame, holder, last_holder in self._target_possession_log:
            dist = abs(hist_frame - frame_idx)
            if dist > window:
                continue
            if holder in self.target_track_ids and dist < best_dist:
                best_dist = dist
                best_track = holder
            if last_holder in self.target_track_ids and dist < best_dist:
                best_dist = dist
                best_track = last_holder
        return best_track

    def _find_scorer_at_frame(self, frame_idx: int) -> int:
        """Find the most likely scorer at a given frame from possession history.

        Searches ±3 seconds. Prefers target tracks over non-target tracks
        when both are plausible holders near the event.
        """
        candidates: list[tuple[int, int]] = []  # (track_id, frame_distance)
        for hist_frame, ps in reversed(self.event_detector.possession_history):
            dist = abs(hist_frame - frame_idx)
            if dist > 90:  # ~3 seconds at 30fps
                continue
            if ps.ball_status == "in_air" and ps.last_holder_track_id >= 0:
                candidates.append((ps.last_holder_track_id, dist))
            elif ps.holder_track_id >= 0:
                candidates.append((ps.holder_track_id, dist))

        if not candidates:
            return -1

        # Prefer target tracks: if any candidate is a target, pick the closest one
        target_candidates = [(tid, d) for tid, d in candidates if tid in self.target_track_ids]
        if target_candidates:
            return min(target_candidates, key=lambda x: x[1])[0]

        # Otherwise pick the closest candidate
        return min(candidates, key=lambda x: x[1])[0]

    def _merge_events(self, heuristic: list[BasketballEvent],
                      classifier: list[BasketballEvent],
                      gap_seconds: float = 3.0) -> list[BasketballEvent]:
        """Merge events from both sources, deduplicating within gap_seconds.

        When both sources detect the same basket, keep the higher-confidence one.
        Events unique to either source are kept as-is.
        """
        all_events = []

        # Start with heuristic events (steals/assists + made baskets)
        for event in heuristic:
            all_events.append(event)

        # Add classifier events that don't overlap with existing made_basket events
        for c_event in classifier:
            is_duplicate = False
            for existing in all_events:
                if (existing.event_type == "made_basket"
                        and abs(existing.timestamp - c_event.timestamp) < gap_seconds):
                    # Overlap — merge: keep heuristic metadata, boost confidence if classifier is higher
                    if c_event.confidence > existing.confidence:
                        existing.confidence = c_event.confidence
                    existing.metadata["classifier_confirmed"] = True
                    # Backfill court coords from classifier if heuristic didn't have them
                    if "court_x" not in existing.metadata and "court_x" in c_event.metadata:
                        existing.metadata["court_x"] = c_event.metadata["court_x"]
                        existing.metadata["court_y"] = c_event.metadata["court_y"]
                    is_duplicate = True
                    break

            if not is_duplicate:
                # Classifier found a basket the heuristic missed
                c_event.metadata["source"] = "classifier_only"
                all_events.append(c_event)
                logger.info(f"Classifier-only made basket at {c_event.timestamp:.1f}s "
                           f"(conf={c_event.confidence:.2f})")

        # Sort by timestamp
        all_events.sort(key=lambda e: e.timestamp)
        return all_events

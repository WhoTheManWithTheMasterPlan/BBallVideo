"""
Celery tasks for video processing pipeline.
"""

import logging
import uuid
from pathlib import Path

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="process_video")
def process_video(self, game_id: str):
    """
    Main video processing task.

    1. Fetch game record + roster data from DB
    2. Run inference pipeline on the video
    3. Extract clips at event timestamps
    4. Write stats, clips, and player records to DB
    5. Update game status
    """
    # Lazy imports — ML libs only available on the GPU worker
    from app.services.video.storage import get_file_path
    from app.services.video.clipper import extract_clip, extract_thumbnail
    from app.services.inference.pipeline import InferencePipeline
    from app.core.database import sync_session
    from app.models.game import Game
    from app.models.clip import Clip
    from app.models.stat import StatEvent
    from app.models.player import Player
    from app.models.roster import Roster

    logger.info(f"Starting processing for game {game_id}")
    self.update_state(state="PROCESSING", meta={"step": "loading"})

    session = sync_session()
    try:
        # --- Step 1: Fetch game and roster data ---
        game = session.get(Game, uuid.UUID(game_id))
        if not game or not game.video_file_key:
            raise ValueError(f"Game {game_id} not found or has no video")

        video_path = str(get_file_path(game.video_file_key))
        if not Path(video_path).exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        logger.info(f"Video path: {video_path}")

        # Build team descriptions for CLIP classifier
        home_color = _get_jersey_color(game.home_roster_id, session)
        away_color = _get_jersey_color(game.away_roster_id, session)
        team_descriptions = [
            f"person wearing {home_color} jersey",
            f"person wearing {away_color} jersey",
        ]
        team_names = [game.home_team, game.away_team]

        # Load roster player embeddings if available
        roster_players = _load_roster_players(game, session)

        # --- Step 2: Run inference pipeline ---
        self.update_state(state="PROCESSING", meta={"step": "inference"})
        logger.info(f"Starting inference: teams={team_names}, roster_players={len(roster_players)}")

        pipeline = InferencePipeline(
            team_descriptions=team_descriptions,
            team_names=team_names,
            roster_players=roster_players,
        )
        events = pipeline.process(video_path)
        logger.info(f"Inference complete: {len(events)} events, {len(pipeline.players)} players")

        # --- Step 3: Extract clips ---
        self.update_state(state="PROCESSING", meta={"step": "clipping", "events": len(events)})
        logger.info(f"Extracting {len(events)} clips...")

        for i, event in enumerate(events):
            try:
                clip_id = uuid.uuid4()
                clip_file_key = f"clips/{game_id}/{clip_id}.mp4"
                thumb_file_key = f"clips/{game_id}/{clip_id}.jpg"

                clip_abs = str(get_file_path(clip_file_key))
                thumb_abs = str(get_file_path(thumb_file_key))

                extract_clip(video_path, clip_abs, event.timestamp, event.timestamp, padding=3.0)
                extract_thumbnail(video_path, thumb_abs, event.timestamp)

                # Resolve roster player ID from track info
                player_info = pipeline.players.get(event.player_track_id)
                roster_player_id = None
                if player_info and player_info.roster_player_id:
                    try:
                        roster_player_id = uuid.UUID(player_info.roster_player_id)
                    except ValueError:
                        pass

                # Write Clip record
                clip = Clip(
                    id=clip_id,
                    game_id=uuid.UUID(game_id),
                    event_type=event.event_type,
                    start_time=max(0, event.timestamp - 3),
                    end_time=event.timestamp + 3,
                    file_key=clip_file_key,
                    thumbnail_file_key=thumb_file_key,
                    player_id=roster_player_id,
                )
                session.add(clip)

                # Write StatEvent record
                stat = StatEvent(
                    game_id=uuid.UUID(game_id),
                    event_type=event.event_type,
                    timestamp=event.timestamp,
                    player_id=roster_player_id,
                    team=event.team,
                    court_x=event.court_x,
                    court_y=event.court_y,
                    metadata_={
                        "jersey_number": event.jersey_number,
                        "player_name": event.player_name,
                        "track_id": event.player_track_id,
                    },
                )
                session.add(stat)

            except Exception as e:
                logger.warning(f"Failed to extract clip {i} at {event.timestamp:.1f}s: {e}")
                continue

        # --- Step 4: Save tracked players ---
        self.update_state(state="PROCESSING", meta={"step": "saving"})
        for track_id, pinfo in pipeline.players.items():
            player = Player(
                name=pinfo.player_name,
                jersey_number=pinfo.jersey_number,
                team=pinfo.team_name,
                track_id=track_id,
                game_id=uuid.UUID(game_id),
            )
            session.add(player)

        # --- Step 5: Update game status ---
        game.status = "completed"
        session.commit()
        logger.info(f"Processing complete for game {game_id}: {len(events)} events, {len(pipeline.players)} players")

    except Exception as e:
        logger.exception(f"Processing failed for game {game_id}: {e}")
        session.rollback()
        try:
            game = session.get(Game, uuid.UUID(game_id))
            if game:
                game.status = "failed"
                session.commit()
        except Exception:
            pass
        raise
    finally:
        session.close()

    return {"game_id": game_id, "status": "completed", "events_count": len(events)}


def _get_jersey_color(roster_id, session) -> str:
    """Get jersey color description from roster, or default."""
    if not roster_id:
        return "colored"
    from app.models.roster import Roster
    roster = session.get(Roster, roster_id)
    if roster and roster.jersey_color_primary:
        return roster.jersey_color_primary
    return "colored"


def _load_roster_players(game, session) -> list[dict]:
    """Load roster players with ReID embeddings for both teams."""
    from app.models.roster import Roster
    players = []
    for roster_id, team_name in [(game.home_roster_id, game.home_team),
                                  (game.away_roster_id, game.away_team)]:
        if not roster_id:
            continue
        roster = session.get(Roster, roster_id)
        if not roster:
            continue
        for rp in roster.players:
            players.append({
                "id": str(rp.id),
                "name": rp.name,
                "jersey_number": rp.jersey_number,
                "team_name": team_name,
                "reid_embedding": rp.reid_embedding,
            })
    return players

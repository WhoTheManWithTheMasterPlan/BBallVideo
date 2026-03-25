"""
Celery tasks for video processing pipeline.
"""

import logging
import tempfile
import uuid
from pathlib import Path

from app.workers.celery_app import celery_app
from app.services.video.storage import copy_file, save_file, get_file_path
from app.services.video.clipper import extract_clip, extract_thumbnail
from app.services.inference.pipeline import InferencePipeline

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="process_video")
def process_video(self, game_id: str):
    """
    Main video processing task.

    1. Read video from local storage
    2. Run inference pipeline
    3. Cut clips at event timestamps
    4. Save clips to local storage
    5. Write stats to database
    """
    logger.info(f"Starting processing for game {game_id}")
    self.update_state(state="PROCESSING", meta={"step": "loading"})

    # TODO: Fetch game record from DB to get video_file_key and team info
    # For now, this is a skeleton showing the flow

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = str(Path(tmpdir) / "game.mp4")

        # Step 1: Copy video from storage to temp dir for processing
        # copy_file(game.video_file_key, video_path)
        self.update_state(state="PROCESSING", meta={"step": "inference"})

        # Step 2: Run inference pipeline
        # pipeline = InferencePipeline(
        #     team_descriptions=["person wearing white jersey", "person wearing dark jersey"],
        #     team_names=[game.home_team, game.away_team],
        # )
        # events = pipeline.process(video_path)

        self.update_state(state="PROCESSING", meta={"step": "clipping"})

        # Step 3: Cut clips for each event
        # for event in events:
        #     clip_path = str(Path(tmpdir) / f"clip_{uuid.uuid4()}.mp4")
        #     extract_clip(video_path, clip_path, event.timestamp - 3, event.timestamp + 3)
        #
        #     thumb_path = str(Path(tmpdir) / f"thumb_{uuid.uuid4()}.jpg")
        #     extract_thumbnail(video_path, thumb_path, event.timestamp)
        #
        #     # Save clip + thumbnail to local storage
        #     clip_file_key = f"clips/{game_id}/{uuid.uuid4()}.mp4"
        #     thumb_file_key = f"clips/{game_id}/{uuid.uuid4()}.jpg"
        #     save_file(clip_file_key, clip_path)
        #     save_file(thumb_file_key, thumb_path)

        self.update_state(state="PROCESSING", meta={"step": "saving"})

        # Step 4: Write events + clips to database
        # TODO: Use sync SQLAlchemy session to write StatEvent and Clip records

    logger.info(f"Processing complete for game {game_id}")
    return {"game_id": game_id, "status": "completed"}

"""
Celery tasks for video processing pipeline.
Player-centric: processes video for a specific profile, filtering to target player events.
"""

import logging
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="process_video")
def process_video(self, job_id: str):
    """
    Main video processing task.

    1. Load ProcessingJob + Video + Profile from DB
    2. Download video from TrueNAS if remote worker
    3. Run inference pipeline with target profile embeddings
    4. Extract highlight clips for detected events
    5. Write Highlight + Stat records to DB
    6. Update job status
    """
    # Lazy imports — ML libs only available on the GPU worker
    from app.services.video.storage import get_file_path
    from app.services.video.clipper import extract_clip, extract_thumbnail
    from app.services.inference.pipeline import InferencePipeline
    from app.core.database import sync_session
    from app.models.job import ProcessingJob
    from app.models.video import Video
    from app.models.profile import Profile
    from app.models.highlight import Highlight
    from app.models.stat import Stat

    logger.info(f"Starting processing for job {job_id}")
    self.update_state(state="PROCESSING", meta={"step": "loading"})

    session = sync_session()
    temp_dir = None
    try:
        # --- Step 1: Load job, video, profile ---
        job = session.get(ProcessingJob, uuid.UUID(job_id))
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.status = "processing"
        job.started_at = datetime.utcnow()
        session.commit()

        video = session.get(Video, job.video_id)
        if not video or not video.file_key:
            raise ValueError(f"Video {job.video_id} not found or has no file")

        profile = session.get(Profile, job.profile_id)
        if not profile:
            raise ValueError(f"Profile {job.profile_id} not found")

        # Load profile photo embeddings
        profile_embeddings = []
        for photo in profile.photos:
            if photo.reid_embedding:
                emb = np.frombuffer(photo.reid_embedding, dtype=np.float32)
                profile_embeddings.append(emb)

        logger.info(f"Profile '{profile.name}': {len(profile_embeddings)} photo embeddings loaded")

        # Build team color descriptions for CLIP classifier
        team_descriptions = []
        team_names = []
        if profile.team_color_primary:
            team_descriptions.append(f"person wearing {profile.team_color_primary} jersey")
            team_names.append("target_team")
            # Add a generic "other team" description
            team_descriptions.append("person wearing different colored jersey")
            team_names.append("opponent")

        # --- Step 2: Resolve video path ---
        if settings.remote_storage_enabled:
            from app.services.video.remote_storage import download_file

            temp_dir = tempfile.mkdtemp(prefix="bballvideo_")
            video_filename = Path(video.file_key).name
            video_path = str(Path(temp_dir) / video_filename)

            self.update_state(state="PROCESSING", meta={"step": "downloading"})
            logger.info("Remote worker — downloading video from TrueNAS")
            download_file(video.file_key, video_path)
        else:
            video_path = str(get_file_path(video.file_key))
            if not Path(video_path).exists():
                raise FileNotFoundError(f"Video file not found: {video_path}")

        logger.info(f"Video path: {video_path}")

        # --- Step 3: Run inference pipeline ---
        self.update_state(state="PROCESSING", meta={"step": "inference"})

        # Resolve hoop model path
        hoop_model_path = None
        if settings.basketball_model_path:
            # Resolve relative to project root (one level up from backend/)
            candidate = Path(__file__).parent.parent.parent.parent / settings.basketball_model_path
            if candidate.exists():
                hoop_model_path = str(candidate)
                logger.info(f"Hoop model: {hoop_model_path}")
            else:
                logger.warning(f"Hoop model not found at {candidate}")

        pipeline = InferencePipeline(
            hoop_model_path=hoop_model_path,
            profile_embeddings=profile_embeddings if profile_embeddings else None,
            profile_jersey_number=profile.jersey_number,
            team_descriptions=team_descriptions if team_descriptions else None,
            team_names=team_names if team_names else None,
        )
        events = pipeline.process(video_path)
        logger.info(f"Inference complete: {len(events)} events for target profile")

        # --- Step 4: Extract highlight clips ---
        self.update_state(state="PROCESSING", meta={"step": "clipping", "events": len(events)})
        logger.info(f"Extracting {len(events)} highlights...")

        clips_base = Path(temp_dir) / "clips" if temp_dir else None
        highlights_written = 0

        for i, event in enumerate(events):
            try:
                highlight_id = uuid.uuid4()
                clip_file_key = f"highlights/{job_id}/{highlight_id}.mp4"
                thumb_file_key = f"highlights/{job_id}/{highlight_id}.jpg"

                if clips_base:
                    clip_abs = str(clips_base / f"{highlight_id}.mp4")
                    thumb_abs = str(clips_base / f"{highlight_id}.jpg")
                else:
                    clip_abs = str(get_file_path(clip_file_key))
                    thumb_abs = str(get_file_path(thumb_file_key))

                extract_clip(video_path, clip_abs, event.timestamp, event.timestamp, padding=5.0)
                extract_thumbnail(video_path, thumb_abs, event.timestamp)

                # Upload if remote worker
                if settings.remote_storage_enabled:
                    from app.services.video.remote_storage import upload_file
                    upload_file(clip_abs, clip_file_key)
                    upload_file(thumb_abs, thumb_file_key)

                # Write Highlight record
                highlight = Highlight(
                    id=highlight_id,
                    job_id=uuid.UUID(job_id),
                    event_type=event.event_type,
                    start_time=max(0, event.timestamp - 5),
                    end_time=event.timestamp + 5,
                    file_key=clip_file_key,
                    thumbnail_file_key=thumb_file_key,
                    confidence=event.confidence,
                    metadata_=event.metadata,
                )
                session.add(highlight)

                # Write Stat record
                stat = Stat(
                    job_id=uuid.UUID(job_id),
                    event_type=event.event_type,
                    timestamp=event.timestamp,
                    metadata_=event.metadata,
                )
                session.add(stat)
                highlights_written += 1

            except Exception as e:
                logger.warning(f"Failed to extract highlight {i} at {event.timestamp:.1f}s: {e}")
                continue

        # --- Step 5: Update job status ---
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.events_count = len(events)
        job.highlights_count = highlights_written
        session.commit()
        logger.info(f"Processing complete for job {job_id}: {len(events)} events, {highlights_written} highlights")

    except Exception as e:
        logger.exception(f"Processing failed for job {job_id}: {e}")
        session.rollback()
        try:
            job = session.get(ProcessingJob, uuid.UUID(job_id))
            if job:
                job.status = "failed"
                job.error_message = str(e)[:1000]
                job.completed_at = datetime.utcnow()
                session.commit()
        except Exception:
            pass
        raise
    finally:
        session.close()
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"Cleaned up temp dir: {temp_dir}")

    return {"job_id": job_id, "status": "completed", "events_count": len(events), "highlights_count": highlights_written}

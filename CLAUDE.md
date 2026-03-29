# BBallVideo

Basketball video analysis platform — AI-powered player-centric game film breakdown.

## Architecture

Monorepo with three main components:
- `backend/` — FastAPI + Celery workers (Python 3.14 on laptop, 3.11+ in Docker)
- `frontend/` — Next.js 14 + shadcn/ui + D3.js
- `ml/` — Custom model training scripts, weights, datasets, platform patches

**Data model (player-centric)**: User → Profile → Video → ProcessingJob → Highlights/Stats.
- **Profile**: A player to track (name + user_id). Legacy fields `jersey_number`, `team_color_primary`, `team_color_secondary`, and `ProfilePhoto` still exist for backward compatibility only.
- **Team**: A team a player belongs to, with jersey_number, colors (primary/secondary), AND photos (TeamPhoto). A Profile can belong to multiple Teams. Team is the source of truth for jersey/color/photo data.
- **Video**: Uploaded game film
- **ProcessingJob**: Links a Video + Profile → runs inference → produces Highlights + Stats. Optionally links to a Team for jersey color context.
- **Highlight**: A clip (made basket, steal, assist) with thumbnail + confidence
- **Stat**: Individual event record with timestamp + metadata

ReID embeddings match tracked players to profile photos, with optional CLIP team classification and EasyOCR jersey number fallback.

## Tech Stack

### Inference Pipeline
- **Player/ball detection**: YOLOv8x (Ultralytics) — COCO classes 0 (person) + 32 (sports ball), BoT-SORT tracking
- **Pose estimation**: YOLOv8m-pose (medium, VRAM-friendly) — COCO skeleton keypoints, heuristic shooting/dribbling classification (`backend/app/services/inference/pose_estimator.py`), runs every 10 frames
- **Ball detection (custom)**: YOLOv8s fine-tuned on Roboflow basketball-ball dataset (`ml/datasets/basketball-ball/runs/detect/ball-detector/weights/best.pt`)
- **Ball tracking**: Kalman filter interpolation across detection gaps (`backend/app/services/inference/ball_tracker.py`) — predicts ball position up to 15 frames without detection
- **Hoop detection**: Separate basketball-specific model (`ml/models/shot-tracker/best.pt`, avishah3) — class 1 (Basketball Hoop)
- **Scoring classifier**: ResNet50 binary classifier on hoop crops (`ml/models/scoring-classifier/resnet50_cropped.pth`, isBre) — per-frame confidence + scipy peak detection
- **Action classifier**: MViT v2-S fine-tuned on SpaceJam dataset (`ml/models/action-classifier/mvit_v2_spacejam.pth`) — 10 basketball action classes (block, pass, run, dribble, shoot, ball_in_hand, defence, pick, no_action, walk). Integrated into pipeline: buffers 16 frames per player crop, classifies actions, enriches events with `action` + `action_confidence` metadata.
- **Court detection**: YOLOv8x-pose on basketball court keypoints (`ml/models/court-detector/best.pt`) — 18 keypoints (corners, free throw, midcourt, paint). Runs every 30 frames. Homography maps player foot positions to normalized court coords for shot charts. Training script: `ml/train_court_detector.py` (Roboflow dataset).
- **Event detection**: Made baskets (ball trajectory through hoop via up→down transition + rim interpolation), steals (cross-team possession change), assists (same-team pass within 5s before basket)
- **Possession tracking**: Frame-by-frame state machine, ball-player proximity, 8-frame confirmation
- **Player re-identification**: ResNet18 fallback (OSNet `osnet_x1_0` not in timm for Py3.14), 3-vote confirmation
- **Team classification**: Fashion CLIP (Marqo/marqo-fashionCLIP, zero-shot jersey color) — optional
- **Jersey number OCR**: EasyOCR (PaddleOCR incompatible with Python 3.14)
- **vid_stride**: Auto-calculated from video FPS to target 30fps

### Backend
- FastAPI (async API)
- Celery + Redis (job queue for video processing)
- PostgreSQL (profiles, videos, jobs, highlights, stats)
- Local filesystem (TrueNAS) for raw video + highlight clips
- Supabase Auth (multi-tenant SaaS auth — not yet integrated)

### Frontend
- Next.js 14 (App Router)
- D3.js (court viz — shot charts)
- Native HTML5 video player (clip playback)

### Infrastructure (Split Architecture)
- **TrueNAS (192.168.68.10)**: FastAPI API (:8001), Next.js frontend (:3001), PostgreSQL (:5432), Redis (:6380), local storage (1TB)
- **Laptop (RTX 3070)**: Celery GPU worker connects to TrueNAS DB + Redis remotely
- Two Dockerfiles for backend: `Dockerfile.api` (lightweight, no ML libs) and `Dockerfile` (full, with torch/YOLO/etc.)
- Two requirements files: `requirements-api.txt` (API only) and `requirements.txt` (full ML stack)

## Commands

```bash
# Deploy to TrueNAS (backend + frontend)
ssh root@192.168.68.10 "cd /mnt/apps/bballvideo/app && git pull && docker compose up -d --build"

# Run GPU worker on laptop (must include ffmpeg in PATH)
cd backend
export PATH="$PATH:/c/Users/schae/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1-full_build/bin"
.venv/Scripts/celery -A app.workers.celery_app worker --loglevel=info --pool=solo -n gpu-worker@ET

# Local dev — backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001

# Local dev — frontend
cd frontend && npm install
npm run dev -- -p 3001

# Trigger processing (via API)
# POST /api/v1/videos/{video_id}/process  (Form: profile_id=<uuid>)

# Check job status
# GET /api/v1/jobs/{job_id}

# Kill zombie celery workers (common issue — check before starting new worker)
taskkill /F /IM celery.exe
wmic process where "name='python.exe'" get ProcessId,CommandLine | findstr celery

# ML Training — run from project root, uses backend/.venv
# Phase 1: Ball detector (YOLOv8s, ~819 images, ~15 min)
.\backend\.venv\Scripts\python -m ml.train_ball_detector
# Phase 2: Action classifier (MViT v2-S, ~37K SpaceJam clips, ~18hrs local)
.\backend\.venv\Scripts\python -m ml.train_action_classifier
# Phase 2 (Kaggle cloud): Copy ml/kaggle_train_action_classifier.py into a Kaggle notebook
#   - Dataset: adamschaechter/spacejam-action-recognition (clips in examples/ folder)
#   - Accelerator: GPU T4 x2, 12hr session limit, auto-checkpoint/resume
#   - Output: /kaggle/working/mvit_v2_spacejam.pth → download to ml/models/action-classifier/
# Phase 3: Scoring classifier — pretrained, no training needed (ml/models/scoring-classifier/resnet50_cropped.pth)
# Phase 4: Court keypoint detector (YOLOv8x-pose, Roboflow dataset, needs ROBOFLOW_API_KEY)
.\backend\.venv\Scripts\python -m ml.train_court_detector
```

## API Routes

```
POST   /api/v1/profiles/                    — Create profile
GET    /api/v1/profiles/?user_id=           — List profiles
GET    /api/v1/profiles/{id}                — Get profile
POST   /api/v1/profiles/{id}/photos         — Upload photo (multipart)
DELETE /api/v1/profiles/{id}/photos/{pid}   — Delete photo

POST   /api/v1/profiles/{id}/teams         — Create team for profile
GET    /api/v1/profiles/{id}/teams          — List teams for profile
PUT    /api/v1/profiles/{id}/teams/{tid}    — Update team
DELETE /api/v1/profiles/{id}/teams/{tid}    — Delete team

POST   /api/v1/profiles/{id}/teams/{tid}/photos         — Upload team photo (multipart)
DELETE /api/v1/profiles/{id}/teams/{tid}/photos/{pid}    — Delete team photo

POST   /api/v1/videos/                      — Create video record
GET    /api/v1/videos/?user_id=             — List videos
GET    /api/v1/videos/{id}                  — Get video
POST   /api/v1/videos/{id}/upload           — Upload video file (multipart, <50MB)
POST   /api/v1/videos/{id}/chunked-upload/init     — Init chunked upload (Form: filename, total_chunks, total_size)
POST   /api/v1/videos/{id}/chunked-upload/chunk    — Upload one chunk (Form: upload_id, chunk_index + File: chunk)
POST   /api/v1/videos/{id}/chunked-upload/complete — Reassemble chunks (Form: upload_id)
POST   /api/v1/videos/{id}/process          — Trigger processing (Form: profile_id, optional team_id)

GET    /api/v1/jobs/{id}                    — Get job status
GET    /api/v1/jobs/profile/{profile_id}    — Jobs by profile
GET    /api/v1/jobs/video/{video_id}        — Jobs by video

GET    /api/v1/highlights/job/{job_id}      — Highlights by job (?event_type=)
GET    /api/v1/highlights/profile/{id}      — Highlights by profile (?event_type=)

GET    /api/v1/stats/job/{job_id}           — Stats by job
GET    /api/v1/stats/profile/{id}/summary   — Aggregate stats by event type

GET    /api/v1/files/{file_key}             — Serve stored files
```

## Data Flow

Camera → Upload video to TrueNAS via API → Create ProcessingJob (video + profile, optional team_id) → Celery task → SCP video to laptop temp dir → YOLO+BoT-SORT (person/ball) + YOLOv8m-pose (skeleton) + best.pt (hoop) → Pipeline loads team-specific photos/colors/jersey when team_id is set on job, falls back to legacy Profile data (ProfilePhoto, profile-level jersey/colors) if no team → ReID match to profile/team embeddings → Possession tracking → Court keypoint detection (every 30 frames) → homography → court_x/court_y per event → Action classification (MViT v2-S, 16-frame player crops) → Event detection (made baskets, steals, assists) → FFmpeg clip extraction → SCP clips back to TrueNAS → Highlight + Stat records (with court_x/court_y) → PostgreSQL → API → Frontend (ShotChart D3 viz on job page)

## Known Issues / Workarounds (Python 3.14 + Windows 11)

- **`platform.system()` / `platform.uname()` WMI hang**: WMI queries hang indefinitely on Win11 + Py3.14. Affects celery, torch, ultralytics, and any library calling `platform.*` functions. **Fix**: `ml/patch_platform.py` monkey-patches `platform.system()`, `platform.uname()`, `platform.platform()`, `platform.processor()`, and `platform.node()`. Import it before torch/ultralytics: `import ml.patch_platform`. Celery also needs direct patches in `celery/platforms.py:55` and `celery/worker/state.py:31` (replace `platform.system()` with `sys.platform` check).
- **OSNet not in timm**: `osnet_x1_0` model unavailable. `reid.py` catches `RuntimeError` and falls back to ResNet18.
- **`lap` package**: Must be installed in venv manually. Ultralytics auto-install targets system Python.
- **FFmpeg**: Installed via `winget install Gyan.FFmpeg` but not auto-added to PATH. Must export PATH in worker start command.
- **Zombie celery processes**: Windows doesn't clean up celery workers properly. Always `taskkill /F /IM celery.exe` and check for orphan python.exe processes before starting a new worker.
- **`--pool=solo`**: Required on Windows (no fork support). Use `-n gpu-worker@ET` for unique node name.
- **DataLoader `workers>0` OOM**: Ultralytics multiprocessing workers cause `MemoryError` during mixup augmentation on Windows. Always use `workers=0` for YOLO training. MViT/torch training scripts already default to `NUM_WORKERS=0` on Windows.
- **Laptop sleep kills pipeline**: Long inference runs (~1.75hr) fail if laptop sleeps — Redis connection drops. Before starting worker: `cmd.exe //c "powercfg /change standby-timeout-ac 0"`. Redis reconnect resilience added to `celery_app.py` as a safety net (`socket_keepalive`, `retry_on_timeout`).

## Ground Rules

### Security — ABSOLUTE
- **NEVER display API keys, passwords, secrets, or tokens in chat.** This includes inside CLI commands, code blocks, logs, or tool outputs. Use placeholders like `<YOUR_KEY>` or direct the user where to set them.
- If a tool output or file contains a secret, redact it before showing in chat.
- Scan code for accidental secret exposure before committing.

### Development Workflow

Every code change follows this process:

#### 1. Pre-Change: Impact Analysis (REQUIRED)
Before modifying any code that touches more than one file or crosses a module boundary, run an **Explore agent** to:
- Trace all imports, call sites, and dependencies of the code being changed
- Identify Pydantic schemas, SQLAlchemy models, and frontend TypeScript types that must stay in sync
- Flag any pipeline coupling (detector → pipeline → worker → API routes → frontend)
- Report findings before writing code

**Skip conditions**: Single-file cosmetic changes, adding new isolated files with no existing dependents.

#### 2. Make the Change
- Write the code the user asked for
- Keep changes focused — don't refactor adjacent code

#### 3. Post-Change: Quality + Documentation (AUTOMATIC)
After any significant change, kick off **two background agents in parallel**:

**Quality Check Agent:**
- Type consistency across backend schemas ↔ models ↔ frontend types
- Import validity — no broken references
- API contract alignment (FastAPI route responses match Pydantic schemas match frontend `api.ts` calls)
- Pipeline data flow integrity (Detection → PlayerInfo → BasketballEvent → Highlight/Stat)
- Flag issues found; fix before moving on

**Documentation Agent:**
- Update CLAUDE.md if architecture, commands, or data flow changed
- Update inline TODOs where integration work is still needed
- Verify the Data Flow section still reflects reality

### Cross-Module Dependency Map

Changes in these areas have high blast radius — always run impact analysis:

```
backend/app/models/*            → schemas, routes, workers, frontend types
backend/app/models/team.py      → TeamPhoto model, schemas, routes (profiles/teams, team photos), workers, frontend types
backend/app/schemas/*           → routes, frontend api.ts, frontend types
backend/app/services/inference/* → pipeline.py, workers/tasks.py
backend/app/workers/tasks.py    → routes/videos.py (trigger endpoint)
frontend/src/types/index.ts     → all frontend components + api.ts
frontend/src/lib/api.ts         → all pages + components that fetch data
docker-compose.yml              → all services, env vars, STORAGE_BASE_PATH
backend/app/services/video/*    → uploads, clip export, remote storage (SCP)
backend/app/services/inference/reid.py → pipeline.py, routes/profiles.py
backend/app/services/inference/court_detector.py → pipeline.py → court_x/court_y in events → tasks.py → Stat → frontend ShotChart
backend/app/services/inference/action_classifier.py → pipeline.py → action metadata in events → Highlight/Stat
```

### Activity Logging (REQUIRED for all frontend changes)

Every frontend page or interactive component MUST include `trackEvent()` calls from `frontend/src/lib/activity.ts`. This is automatic — treat it as part of any frontend change, not a separate task.

**Required tracking points:**
- `page_view` — on mount (`useEffect`) for every page/route
- User actions — clicks on buttons, form submissions, filter changes, navigation events
- Key workflows — upload started/completed, processing triggered, review actions, clip creation, reel building

**Pattern:**
```typescript
import { trackEvent } from "@/lib/activity";

// On page mount
useEffect(() => { trackEvent("page_view", { page: "page_name" }); }, []);

// On user action
onClick={() => { trackEvent("action_name", { relevant: "details" }); doAction(); }}
```

**Backend:** `POST /api/v1/activity/track` receives events. `ActivityLogMiddleware` in `backend/app/middleware/activity_logger.py` also logs all HTTP requests to `{STORAGE_BASE_PATH}/logs/activity.log` (JSON lines, 10MB × 5 rotating).

### Commit Discipline
- Never commit secrets or .env files
- Run quality check before any commit
- Commit messages must reference what component was changed (e.g. "backend/inference: add shot detection logic")

# BBallVideo

Basketball video analysis platform — AI-powered game film breakdown for coaches.

## Architecture

Monorepo with three main components:
- `backend/` — FastAPI + Celery workers (Python 3.11+)
- `frontend/` — Next.js 14 + shadcn/ui + D3.js
- `ml/` — YOLO training configs, model weights, notebooks

Roster management is built into the backend — coaches upload player photos, and the inference pipeline uses OSNet ReID embeddings to match tracked players to roster entries before falling back to CLIP/OCR.

## Tech Stack

### Inference Pipeline
- **Player/ball detection**: YOLOv8 (Ultralytics)
- **Player tracking**: ByteTrack (built into Ultralytics)
- **Team classification**: Fashion CLIP (zero-shot, jersey color)
- **Jersey number OCR**: PaddleOCR
- **Court mapping**: OpenCV homography
- **Player re-identification**: OSNet (via timm)
- **Event detection**: Custom YOLO classes (made shot, turnover, etc.)

### Backend
- FastAPI (async API)
- Celery + Redis (job queue for video processing)
- PostgreSQL (players, games, stats, clips)
- Local filesystem (TrueNAS) (raw video + clips)
- Supabase Auth (multi-tenant SaaS auth)

### Frontend
- Next.js 14 (App Router)
- shadcn/ui (components)
- Video.js (timestamped clip playback)
- D3.js (court viz — heatmaps, player paths, shot charts)
- Recharts (stat dashboards)

### Infrastructure
- TrueNAS local storage (1TB limit)
- Docker Compose on TrueNAS (all services)
- GPU inference on TrueNAS (Tesla T4 / RTX A2000)

## Commands

```bash
# Backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend && npm install
npm run dev

# Workers
celery -A app.workers.celery_app worker --loglevel=info

# Docker (full stack local)
docker compose up

# Storage base path (set in .env or environment)
# STORAGE_BASE_PATH=/mnt/bball-video  (TrueNAS dataset mount point)
```

## Data Flow

Camera → Upload to TrueNAS → Celery Job → YOLO → ByteTrack → ReID (roster match) → CLIP/OCR (fallback) → Events → FFmpeg clips → PostgreSQL stats → Coach Dashboard

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
- Flag any pipeline coupling (detector → classifier → OCR → pipeline → worker → API routes → frontend)
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
- Pipeline data flow integrity (Detection → PlayerInfo → GameEvent → StatEvent → ClipResponse)
- Flag issues found; fix before moving on

**Documentation Agent:**
- Update CLAUDE.md if architecture, commands, or data flow changed
- Update inline TODOs where integration work is still needed
- Verify the Data Flow section still reflects reality

### Cross-Module Dependency Map

Changes in these areas have high blast radius — always run impact analysis:

```
backend/app/models/*        → schemas, routes, workers, frontend types
backend/app/schemas/*       → routes, frontend api.ts, frontend types
backend/app/services/inference/* → pipeline.py, workers/tasks.py
backend/app/workers/tasks.py    → routes/uploads.py (trigger endpoint)
frontend/src/types/index.ts     → all frontend components + api.ts
frontend/src/lib/api.ts         → all pages + components that fetch data
docker-compose.yml              → all services, env vars, STORAGE_BASE_PATH
backend/app/services/storage/*  → uploads, clip export, any file I/O (local filesystem)
backend/app/models/roster.py    → schemas/roster.py, routes/roster.py, workers/tasks.py
backend/app/services/inference/reid.py → pipeline.py, routes/roster.py
```

### Commit Discipline
- Never commit secrets or .env files
- Run quality check before any commit
- Commit messages must reference what component was changed (e.g. "backend/inference: add shot detection logic")

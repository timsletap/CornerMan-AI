# CornerMan AI

[![CI](https://github.com/timsletap/CornerMan-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/timsletap/CornerMan-AI/actions/workflows/ci.yml)

AI-powered MMA and striking analysis platform. Upload fight footage or import from YouTube, and get real-time skeleton tracking, strike detection, guard analysis, and AI coaching feedback.

## What It Does

- **YOLOv8-Pose Skeleton Tracking** - Detects 17 COCO keypoints per frame to track fighter movement
- **Strike Detection** - Identifies jabs, crosses, hooks, uppercuts, body shots via wrist velocity spikes and biomechanical heuristics
- **Guard Analysis** - Measures off-hand distance from chin during strikes to flag dropped guard
- **Telegraph Detection** - Spots elbow flare (chicken wing) in pre-strike frames
- **Annotated Video** - Generates a video overlay with skeleton lines, strike markers, velocity vectors, guard distance lines, and a live HUD
- **AI Coaching** - Claude AI analyzes the vision data and delivers feedback in a direct corner-coach persona
- **Drill Recommendations** - Maps detected errors to specific training drills

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 16, React 19, Tailwind CSS 4, TypeScript |
| Backend | FastAPI, SQLAlchemy, Alembic, Pydantic |
| Vision | YOLOv8-Pose (Ultralytics), OpenCV, NumPy |
| AI | Anthropic Claude API |
| Task Queue | Celery + Redis |
| Database | PostgreSQL 16 |
| Video | FFmpeg, yt-dlp |
| Infra | Docker Compose |

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Git

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/timsletap/CornerMan-AI.git
cd CornerMan-AI
```

### 2. Set up environment variables

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and configure:

- **`DATABASE_URL`** - Change `localhost` to `db` for Docker: `postgresql://cornerman:cornerman@db:5432/cornerman`
- **`REDIS_URL`** - Change `localhost` to `redis` for Docker: `redis://redis:6379/0`
- **`SECRET_KEY`** - Set to a random string for JWT signing (with `APP_ENV=production` the app refuses to start unless it is at least 32 bytes, not the default, and `DEBUG=false`)
- **`ANTHROPIC_API_KEY`** - (Optional) Your Anthropic API key for AI coaching. Without it, basic coaching feedback is generated from vision metrics.

### 3. Start all services

```bash
docker compose up -d
```

This starts:
- **PostgreSQL** on port 5432
- **Redis** on port 6379
- **FastAPI backend** on port 8000
- **Celery worker** for async analysis
- **Next.js frontend** on port 3000

### 4. Run database migrations

```bash
docker compose exec app alembic upgrade head
```

### 5. Open the app

Go to **http://localhost:3000**

1. Register an account
2. Upload a fight video or import from YouTube
3. Click "Analyze" on any video
4. Watch real-time progress as the pipeline runs
5. View results with annotated tracking video, stats, coaching feedback, and drill recommendations

## Running Frontend Locally (Alternative)

If you want hot-reload on the frontend without Docker:

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the backend at `http://localhost:8000` (set via `NEXT_PUBLIC_API_URL` in `frontend/.env.local`).

## Project Structure

```
CornerMan-AI/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # FastAPI route handlers
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── services/        # Business logic (vision, coaching, YouTube, video)
│   │   ├── tasks/           # Celery async tasks
│   │   ├── core/            # Security, exceptions
│   │   ├── config.py        # App configuration (Pydantic settings)
│   │   ├── database.py      # DB engine + session
│   │   └── main.py          # FastAPI app entry point
│   ├── alembic/             # Database migrations
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/             # Next.js pages (App Router)
│   │   ├── components/      # React components
│   │   ├── context/         # Auth context provider
│   │   └── lib/             # API client, types
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
└── README.md
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/users/register` | Create account |
| POST | `/api/v1/users/login` | Get JWT token |
| GET | `/api/v1/users/me` | Current user profile |
| POST | `/api/v1/videos/upload` | Upload video file |
| GET | `/api/v1/videos/{id}/stream` | Stream video |
| POST | `/api/v1/videos/{id}/analyze` | Start analysis |
| GET | `/api/v1/sessions/{id}` | Get analysis results |
| GET | `/api/v1/sessions/{id}/progress` | Real-time analysis progress |
| GET | `/api/v1/sessions/{id}/annotated-stream` | Stream annotated tracking video |
| DELETE | `/api/v1/sessions/{id}` | Delete analysis session |
| POST | `/api/v1/youtube/search` | Search YouTube clips |
| POST | `/api/v1/youtube/download` | Import YouTube video |

## Analysis Pipeline

1. **Pose Extraction** - YOLOv8-Pose runs on every frame, selecting the primary actor by bbox size + center proximity
2. **Occlusion Handling** - Pauses analysis when the subject is occluded for >0.5s
3. **Strike Detection** - Wrist velocity peak detection with 0.3s debounce, classified by biomechanics
4. **Guard Analysis** - Off-hand wrist-to-nose distance normalized by torso height
5. **Telegraph Detection** - Elbow x-coordinate variance in 10 pre-strike frames
6. **Annotated Video Rendering** - Skeleton overlay, HUD, strike/error markers, transcoded to h264
7. **AI Coaching** - Claude analyzes the vision JSON with a corner-coach persona
8. **Drill Mapping** - Error types mapped to training drills deterministically

## Configuration

Key settings in `backend/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_VIDEO_DURATION_SECONDS` | 1800 | Max video length (30 min) |
| `MAX_VIDEO_SIZE_MB` | 2000 | Max upload size |
| `FREE_TIER_DAILY_UPLOADS` | 999 | Daily analysis limit |
| `YOLO_MODEL_NAME` | yolov8m-pose.pt | YOLO model variant |
| `VISION_FRAME_SKIP` | 1 | Analyze every Nth frame |
| `STRIKE_VELOCITY_THRESHOLD` | 15.0 | Wrist velocity threshold for strike detection |
| `GUARD_DISTANCE_THRESHOLD` | 0.35 | Normalized guard distance threshold |
| `ANTHROPIC_API_KEY` | (empty) | Set for AI coaching |

## Troubleshooting

**"Failed to fetch" on login/register** - Backend isn't running. Make sure Docker Desktop is open and `docker compose up -d` completed.

**Analysis stuck in queue** - Check the Celery worker: `docker compose logs celery-worker --tail 20`. Restart with `docker compose restart celery-worker`.

**Grey/blank annotated video** - The video was likely AV1 encoded. Re-import the video; yt-dlp now downloads h264 and transcodes automatically.

**Port 3000 already in use** - Stop local Next.js dev server or change the port in `docker-compose.yml`.

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.config import settings
from app.database import SessionLocal
from app.schemas.common import HealthResponse
from app.services.seed_drills import seed_drills

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: seed drills table
    db = SessionLocal()
    try:
        seed_drills(db)
        logger.info("Drill seed data loaded")
    except Exception:
        logger.exception("Failed to seed drills")
    finally:
        db.close()
    yield
    # Shutdown


app = FastAPI(
    title="CornerMan AI",
    description="MMA/Striking Analysis Platform API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check() -> dict:
    return {"status": "ok", "version": "0.1.0"}

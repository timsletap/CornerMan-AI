from fastapi import APIRouter

from app.api.v1 import analysis, drills, media, users, videos, youtube

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(users.router)
api_v1_router.include_router(videos.router)
api_v1_router.include_router(analysis.router)
api_v1_router.include_router(drills.router)
api_v1_router.include_router(youtube.router)
api_v1_router.include_router(media.router)

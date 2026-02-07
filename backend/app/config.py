import json
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://cornerman:cornerman@localhost:5432/cornerman"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "change-me-to-a-random-secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_ALGORITHM: str = "HS256"

    # AWS S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "cornerman-videos"

    # App
    APP_ENV: str = "development"
    DEBUG: bool = True
    CORS_ORIGINS: str = '["http://localhost:3000"]'

    # Anthropic Claude
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    ANTHROPIC_MAX_TOKENS: int = 1500

    # Vision Engine Thresholds
    STRIKE_VELOCITY_THRESHOLD: float = 15.0
    GUARD_DISTANCE_THRESHOLD: float = 0.35
    TELEGRAPH_VARIANCE_THRESHOLD: float = 0.10
    OCCLUSION_CONFIDENCE_THRESHOLD: float = 0.7
    OCCLUSION_PAUSE_SECONDS: float = 0.5
    YOLO_MODEL_NAME: str = "yolov8m-pose.pt"
    VISION_FRAME_SKIP: int = 1

    # Video Storage
    VIDEO_UPLOAD_DIR: str = "uploads/videos"
    STORAGE_BACKEND: str = "local"

    # Limits
    FREE_TIER_DAILY_UPLOADS: int = 3
    MAX_VIDEO_DURATION_SECONDS: int = 60
    MAX_VIDEO_SIZE_MB: int = 500
    API_CREDIT_HOURLY_LIMIT: float = 5.00
    CLAUDE_COST_PER_CALL: float = 0.015

    @property
    def cors_origins_list(self) -> list[str]:
        return json.loads(self.CORS_ORIGINS)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

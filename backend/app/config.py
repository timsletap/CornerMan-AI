import json
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings

DEFAULT_SECRET_KEY = "change-me-to-a-random-secret-key"
MIN_SECRET_KEY_BYTES = 32


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://cornerman:cornerman@localhost:5432/cornerman"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = DEFAULT_SECRET_KEY
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
    ANTHROPIC_MODEL: str = "claude-opus-5-5"
    ANTHROPIC_MAX_TOKENS: int = 1500
    # USD per million tokens for ANTHROPIC_MODEL; update both when changing the model
    ANTHROPIC_PRICE_INPUT_PER_MTOK: float = 4.00
    ANTHROPIC_PRICE_OUTPUT_PER_MTOK: float = 20.00

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
    MEDIA_URL_TTL_SECONDS: int = 300

    # Limits
    FREE_TIER_DAILY_UPLOADS: int = 5
    MAX_VIDEO_DURATION_SECONDS: int = 1800
    MAX_VIDEO_SIZE_MB: int = 500
    API_CREDIT_HOURLY_LIMIT: float = 1.00

    @model_validator(mode="after")
    def _fail_safe_in_production(self) -> Self:
        if self.APP_ENV != "production":
            return self
        if self.SECRET_KEY == DEFAULT_SECRET_KEY:
            raise ValueError("SECRET_KEY must be changed from the default in production")
        if len(self.SECRET_KEY.encode()) < MIN_SECRET_KEY_BYTES:
            raise ValueError(
                f"SECRET_KEY must be at least {MIN_SECRET_KEY_BYTES} bytes in production"
            )
        if self.DEBUG:
            raise ValueError("DEBUG must be false in production")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return json.loads(self.CORS_ORIGINS)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

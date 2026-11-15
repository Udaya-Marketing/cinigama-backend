import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Event Photo Management & Face Recognition"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # CORS Configuration
    CORS_ORIGINS: List[str] | str = [
        "https://www.cinigama.in",
        "https://cinigama.in",
        "http://localhost:3000",
                "http://localhost:3001",

        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    CORS_ORIGIN_REGEX: str = r"^https?://(.*\.)?(cinigama\.in|vercel\.app|localhost|127\.0\.0\.1)(:[0-9]+)?$"

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "event_photos"
    DATABASE_URL: str | None = None
    SYNC_DATABASE_URL: str | None = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # JWT Authentication
    JWT_SECRET_KEY: str = "super-secret-key-change-me-in-production-min-32-chars-long"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Storage Backend ('r2' or 'local')
    STORAGE_BACKEND: str = "r2"
    STORAGE_BASE_DIR: Path = (
        Path("/tmp/storage")
        if (os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
        else Path("storage")
    )
    MODELS_DIR: Path = Path("models_zoo")
    YUNET_MODEL_FILE: str = "face_detection_yunet_2023mar.onnx"
    SFACE_MODEL_FILE: str = "face_recognition_sface_2021dec.onnx"

    # Cloudflare R2 Settings
    R2_ACCOUNT_ID: str | None = None
    R2_ACCESS_KEY_ID: str | None = None
    R2_SECRET_ACCESS_KEY: str | None = None
    R2_BUCKET_NAME: str = "cinigama-storage"
    R2_ENDPOINT_URL: str | None = None
    R2_PRESIGNED_EXPIRY_SECONDS: int = 900

    # Image Processing & Upload Limits
    MAX_UPLOAD_SIZE_MB: int = 35
    ALLOWED_IMAGE_MIMES: List[str] = ["image/jpeg", "image/png", "image/webp"]
    MAX_IMAGE_DIMENSION_PX: int = 8192
    THUMBNAIL_MAX_DIMENSION_PX: int = 800
    THUMBNAIL_WEBP_QUALITY: int = 80

    # Face Recognition Engine Parameters
    YUNET_SCORE_THRESHOLD: float = 0.70
    YUNET_NMS_THRESHOLD: float = 0.30
    YUNET_TOP_K: int = 5000
    # Calibrated SFace cosine similarity threshold.
    # SFace embeddings are L2 normalized. Cosine similarity ranges from -1 to 1.
    # Default conservative operating threshold: 0.363 (recommended by SFace authors, verified in calibration)
    SFACE_COSINE_THRESHOLD: float = 0.363
    MIN_FACE_SIZE_PX: int = 40
    MAX_SELFIE_FACES_ALLOWED: int = 1

    # Worker Settings
    WORKER_POLL_INTERVAL_SECONDS: float = 2.0
    WORKER_BATCH_SIZE: int = 5
    WORKER_MAX_ATTEMPTS: int = 3
    WORKER_LOCK_TIMEOUT_SECONDS: int = 300

    # Privacy & Security (DPDP Act Compliance)
    BIOMETRIC_DATA_RETENTION_DAYS: int = 365
    SEARCH_SESSION_EXPIRE_MINUTES: int = 30
    DELETE_TEMP_SELFIES: bool = True
    RATE_LIMIT_SEARCH_PER_MINUTE: int = 15

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        if isinstance(self.CORS_ORIGINS, str):
            return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        return self.CORS_ORIGINS

    def get_database_url(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = "postgresql+asyncpg://" + url[len("postgres://"):]
            elif url.startswith("postgresql://"):
                url = "postgresql+asyncpg://" + url[len("postgresql://"):]
            elif url.startswith("postgresql+psycopg2://"):
                url = "postgresql+asyncpg://" + url[len("postgresql+psycopg2://"):]

            # asyncpg requires 'ssl=' instead of 'sslmode='
            if "sslmode=" in url:
                url = url.replace("sslmode=", "ssl=")
            return url
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    def get_sync_database_url(self) -> str:
        if self.SYNC_DATABASE_URL:
            url = self.SYNC_DATABASE_URL
            if url.startswith("postgres://"):
                url = "postgresql+psycopg2://" + url[len("postgres://"):]
            elif url.startswith("postgresql://"):
                url = "postgresql+psycopg2://" + url[len("postgresql://"):]
            return url
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = "postgresql+psycopg2://" + url[len("postgres://"):]
            elif url.startswith("postgresql://"):
                url = "postgresql+psycopg2://" + url[len("postgresql://"):]
            elif url.startswith("postgresql+asyncpg://"):
                url = "postgresql+psycopg2://" + url[len("postgresql+asyncpg://"):]

            # psycopg2 requires 'sslmode=' instead of 'ssl='
            if "ssl=" in url and "sslmode=" not in url:
                url = url.replace("ssl=", "sslmode=")
            return url
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def yunet_path(self) -> Path:
        return self.MODELS_DIR / self.YUNET_MODEL_FILE

    @property
    def sface_path(self) -> Path:
        return self.MODELS_DIR / self.SFACE_MODEL_FILE


settings = Settings()


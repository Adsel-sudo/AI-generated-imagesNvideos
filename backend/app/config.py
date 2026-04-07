from pathlib import Path

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_GOOGLE_IMAGE_MODEL = "gemini-3.1-flash-image-preview"
DEFAULT_GOOGLE_VIDEO_MODEL = "veo-3.1-fast-generate-001"
DEFAULT_PROMPT_OPTIMIZER_MODEL = "gemini-3-flash-preview"


class Settings(BaseSettings):
    redis_url: str = Field(default="redis://redis:6379/0", validation_alias="REDIS_URL")
    database_url: str = Field(default="sqlite:///data/db/app.db", validation_alias="DATABASE_URL")
    session_secret: str = Field(default="dev-session-secret-change-me", validation_alias="SESSION_SECRET")
    session_cookie_name: str = Field(default="ai_workbench_session", validation_alias="SESSION_COOKIE_NAME")

    data_dir: Path = Path("data")
    outputs_dir: Path = Path("data/outputs")
    uploads_dir: Path = Path("data/uploads")
    zips_dir: Path = Path("data/zips")
    logs_dir: Path = Path("data/logs")

    # Google provider settings.
    google_api_key: str | None = Field(default=None, validation_alias="GOOGLE_API_KEY")
    google_genai_api_key: str | None = Field(default=None, validation_alias="GOOGLE_GENAI_API_KEY")
    google_image_backend: str = Field(default="google_genai", validation_alias="GOOGLE_IMAGE_BACKEND")
    google_image_model: str = Field(
        default=DEFAULT_GOOGLE_IMAGE_MODEL,
        validation_alias="GOOGLE_IMAGE_MODEL",
    )
    google_video_model: str = Field(
        default=DEFAULT_GOOGLE_VIDEO_MODEL,
        validation_alias="GOOGLE_VIDEO_MODEL",
    )
    google_image_collage_guard_enabled: bool = Field(
        default=True,
        validation_alias="GOOGLE_IMAGE_COLLAGE_GUARD_ENABLED",
    )
    google_image_retry_on_collage: bool = Field(
        default=True,
        validation_alias="GOOGLE_IMAGE_RETRY_ON_COLLAGE",
    )
    google_image_max_attempts_multiplier: int = Field(
        default=2,
        ge=1,
        le=8,
        validation_alias="GOOGLE_IMAGE_MAX_ATTEMPTS_MULTIPLIER",
    )
    google_image_generate_timeout_seconds: int = Field(
        default=180,
        ge=5,
        le=1800,
        validation_alias="GOOGLE_IMAGE_GENERATE_TIMEOUT_SECONDS",
    )
    google_image_reference_max_edge: int = Field(
        default=2048,
        ge=256,
        le=8192,
        validation_alias="GOOGLE_IMAGE_REFERENCE_MAX_EDGE",
    )
    google_image_reference_jpeg_quality: int = Field(
        default=90,
        ge=50,
        le=100,
        validation_alias="GOOGLE_IMAGE_REFERENCE_JPEG_QUALITY",
    )
    google_image_reference_convert_enabled: bool = Field(
        default=True,
        validation_alias="GOOGLE_IMAGE_REFERENCE_CONVERT_ENABLED",
    )
    prompt_optimizer_model: str = Field(
        default=DEFAULT_PROMPT_OPTIMIZER_MODEL,
        validation_alias="PROMPT_OPTIMIZER_MODEL",
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @computed_field
    @property
    def db_dir(self) -> Path:
        return self.data_dir / "db"

    @field_validator("google_image_model", mode="before")
    @classmethod
    def normalize_google_image_model(cls, value: str | None) -> str:
        normalized = (value or "").strip()
        return normalized or DEFAULT_GOOGLE_IMAGE_MODEL

    @field_validator("google_video_model", mode="before")
    @classmethod
    def normalize_google_video_model(cls, value: str | None) -> str:
        normalized = (value or "").strip()
        return normalized or DEFAULT_GOOGLE_VIDEO_MODEL

    @field_validator("prompt_optimizer_model", mode="before")
    @classmethod
    def normalize_prompt_optimizer_model(cls, value: str | None) -> str:
        normalized = (value or "").strip()
        return normalized or DEFAULT_PROMPT_OPTIMIZER_MODEL


settings = Settings()

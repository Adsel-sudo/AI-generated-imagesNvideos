from pathlib import Path

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_GOOGLE_IMAGE_MODEL = "gemini-3.1-flash-image-preview"
DEFAULT_GOOGLE_VIDEO_MODEL = "veo-2.0-generate"
DEFAULT_PROMPT_OPTIMIZER_MODEL = "gemini-2.0-flash"


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    database_url: str = "sqlite:///data/db/app.db"

    data_dir: Path = Path("data")
    outputs_dir: Path = Path("data/outputs")
    uploads_dir: Path = Path("data/uploads")
    zips_dir: Path = Path("data/zips")
    logs_dir: Path = Path("data/logs")

    # Google provider settings.
    google_api_key: str | None = None
    google_genai_api_key: str | None = None
    google_image_backend: str = "google_genai"
    google_image_model: str = DEFAULT_GOOGLE_IMAGE_MODEL
    google_video_model: str = DEFAULT_GOOGLE_VIDEO_MODEL
    prompt_optimizer_model: str = DEFAULT_PROMPT_OPTIMIZER_MODEL

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

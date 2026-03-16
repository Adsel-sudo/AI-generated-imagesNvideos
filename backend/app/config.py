from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    google_image_model: str = "gemini-3.1-flash-image-preview"
    google_video_model: str = "veo-2.0-generate"
    prompt_optimizer_model: str = "gemini-2.0-flash"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @computed_field
    @property
    def db_dir(self) -> Path:
        return self.data_dir / "db"


settings = Settings()

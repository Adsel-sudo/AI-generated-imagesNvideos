from pathlib import Path

from .config import settings


def ensure_data_dirs() -> None:
    for folder in [
        settings.uploads_dir,
        settings.outputs_dir,
        settings.zips_dir,
        settings.logs_dir,
        settings.db_dir,
    ]:
        folder.mkdir(parents=True, exist_ok=True)


def get_task_output_dir(task_id: str) -> Path:
    return settings.outputs_dir / task_id


def get_task_zip_path(task_id: str) -> Path:
    return settings.zips_dir / f"{task_id}.zip"

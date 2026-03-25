from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel

from .constants import DEFAULT_N_OUTPUTS
from .enums import TaskStatus, TaskType


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Task(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    type: str = Field(default=TaskType.IMAGE.value)
    status: str = Field(default=TaskStatus.QUEUED.value, index=True)
    provider: Optional[str] = None
    params_json: Optional[str] = None
    celery_task_id: Optional[str] = None
    request_text: str
    prompt_final: Optional[str] = None
    model_name: Optional[str] = None
    n_outputs: int = Field(default=DEFAULT_N_OUTPUTS)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None


class Output(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    task_id: str = Field(index=True, foreign_key="task.id")
    index: int
    file_path: str
    mime_type: str = "image/png"
    file_type: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    checksum: Optional[str] = None
    target_type: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Task(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    type: str
    status: str = "pending"
    provider: Optional[str] = None
    params_json: Optional[str] = None
    celery_task_id: Optional[str] = None
    request_text: str
    prompt_final: Optional[str] = None
    model_name: Optional[str] = None
    n_outputs: int = 1
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
    created_at: datetime = Field(default_factory=utcnow)

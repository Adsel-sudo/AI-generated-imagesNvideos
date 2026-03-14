from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from .constants import DEFAULT_PROVIDER
from .enums import TaskType


class StandardTaskParams(BaseModel):
    # Unified platform-level params. Providers can map from this schema to backend-specific args.
    size: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[str] = None
    style: Optional[str] = None
    seed: Optional[int] = None
    negative_prompt: Optional[str] = None
    duration_seconds: Optional[float] = None
    fps: Optional[int] = None
    extra: dict[str, Any] = Field(default_factory=dict)


class CreateTaskRequest(BaseModel):
    type: str = Field(default=TaskType.IMAGE.value)
    provider: Optional[str] = Field(default=DEFAULT_PROVIDER)
    params: dict[str, Any] = Field(default_factory=dict)
    request_text: str
    n_outputs: int = Field(default=1, ge=1, le=12)


class OutputResponse(BaseModel):
    id: str
    task_id: str
    index: int
    file_path: str
    mime_type: str
    file_type: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    checksum: Optional[str] = None
    created_at: datetime


class TaskResponse(BaseModel):
    id: str
    type: str
    status: str
    provider: Optional[str] = None
    params_json: Optional[str] = None
    celery_task_id: Optional[str] = None
    request_text: str
    prompt_final: Optional[str] = None
    model_name: Optional[str] = None
    n_outputs: int
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    outputs: list[OutputResponse] = []

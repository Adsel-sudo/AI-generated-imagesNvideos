from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from .constants import DEFAULT_N_OUTPUTS, DEFAULT_PROVIDER, DEFAULT_TASK_TYPE


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
    # Defaults are centralized in constants so API defaults can evolve with settings in one place.
    type: str = Field(default=DEFAULT_TASK_TYPE)
    provider: Optional[str] = Field(default=DEFAULT_PROVIDER)
    params: dict[str, Any] = Field(default_factory=dict)
    request_text: str
    n_outputs: int = Field(default=DEFAULT_N_OUTPUTS, ge=1, le=12)


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
    target_type: Optional[str] = None
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
    progress_current: int = 0
    progress_total: int = 0
    progress_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    outputs: list[OutputResponse] = Field(default_factory=list)


class ReferenceInput(BaseModel):
    file_path: str
    role: str


class GenerationTargetInput(BaseModel):
    target_type: str
    aspect_ratio: Optional[str] = None
    width: Optional[int] = Field(default=None, gt=0)
    height: Optional[int] = Field(default=None, gt=0)
    n_outputs: int = Field(default=DEFAULT_N_OUTPUTS, ge=1, le=12)


class PromptOptimizeRequest(BaseModel):
    task_type: str = Field(default=DEFAULT_TASK_TYPE)
    raw_request: str
    references: list[ReferenceInput] = Field(default_factory=list)
    usage_options: dict[str, Any] = Field(default_factory=dict)
    generation_targets: list[GenerationTargetInput] = Field(default_factory=list)


class PromptOptimizeResponse(BaseModel):
    structured_summary: dict[str, Any]
    optimized_prompt_cn: str
    generation_prompt: str
    normalized_params: dict[str, Any]


class PromptGenerateTaskRequest(BaseModel):
    task_type: str = Field(default=DEFAULT_TASK_TYPE)
    provider: Optional[str] = Field(default=DEFAULT_PROVIDER)
    optimized_prompt_cn: str
    generation_prompt: str
    structured_summary: dict[str, Any] = Field(default_factory=dict)
    references: list[ReferenceInput] = Field(default_factory=list)
    generation_targets: list[GenerationTargetInput] = Field(default_factory=list)
    usage_options: dict[str, Any] = Field(default_factory=dict)
    confirm_notes: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    n_outputs: int = Field(default=DEFAULT_N_OUTPUTS, ge=1, le=12)


class FileUploadResponse(BaseModel):
    file_id: str
    file_name: str
    file_path: str
    mime_type: str
    file_size: int
    url: Optional[str] = None

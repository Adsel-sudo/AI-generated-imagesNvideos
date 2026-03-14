from abc import ABC, abstractmethod

from ..enums import TaskType
from ..models import Task
from .types import ProviderResultItem


class BaseProvider(ABC):
    name: str = "provider"
    supports_image: bool = False
    supports_video: bool = False
    supports_prompt: bool = False

    def validate_task_type(self, task: Task) -> None:
        task_type = (task.type or "").strip().lower()
        if task_type == TaskType.IMAGE.value and not self.supports_image:
            raise ValueError(f"[provider={self.name}][stage=validate] does not support image tasks")
        if task_type == TaskType.VIDEO.value and not self.supports_video:
            raise ValueError(f"[provider={self.name}][stage=validate] does not support video tasks")
        if task_type == TaskType.PROMPT.value and not self.supports_prompt:
            raise ValueError(f"[provider={self.name}][stage=validate] does not support prompt tasks")

    @abstractmethod
    def generate(self, task: Task) -> list[ProviderResultItem]:
        """Generate outputs for a task and return normalized output metadata."""

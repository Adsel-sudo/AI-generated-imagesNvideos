from abc import ABC, abstractmethod

from ..models import Task
from .types import ProviderResultItem


class BaseProvider(ABC):
    name: str = "provider"
    supports_image: bool = False
    supports_video: bool = False

    def validate_task_type(self, task: Task) -> None:
        task_type = (task.type or "").strip().lower()
        if task_type == "image" and not self.supports_image:
            raise ValueError(f"[{self.name}] does not support image tasks")
        if task_type == "video" and not self.supports_video:
            raise ValueError(f"[{self.name}] does not support video tasks")

    @abstractmethod
    def generate(self, task: Task) -> list[ProviderResultItem]:
        """Generate outputs for a task and return normalized output metadata."""

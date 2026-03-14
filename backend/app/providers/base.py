from abc import ABC, abstractmethod

from ..models import Task
from .types import ProviderResultItem


class BaseProvider(ABC):
    supports_image: bool = False
    supports_video: bool = False

    @abstractmethod
    def generate(self, task: Task) -> list[ProviderResultItem]:
        """Generate outputs for a task and return normalized output metadata."""

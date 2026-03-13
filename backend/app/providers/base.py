from abc import ABC, abstractmethod

from ..models import Task


class BaseProvider(ABC):
    @abstractmethod
    def generate(self, task: Task) -> list[dict]:
        """Generate outputs for a task and return output metadata."""

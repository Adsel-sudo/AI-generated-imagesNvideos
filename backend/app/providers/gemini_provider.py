from ..models import Task
from .base import BaseProvider
from .types import ProviderResultItem


class GeminiProvider(BaseProvider):
    supports_image = True
    supports_video = False

    def generate(self, task: Task) -> list[ProviderResultItem]:
        raise NotImplementedError("Gemini provider is not implemented yet")

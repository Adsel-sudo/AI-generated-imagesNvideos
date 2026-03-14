from ..config import settings
from ..models import Task
from .base import BaseProvider
from .types import ProviderResultItem


class GeminiProvider(BaseProvider):
    """Legacy alias provider. Keep this for compatibility with existing `provider=gemini` requests.

    Future plan: route this alias to GoogleImageProvider implementation.
    """

    name = "gemini"
    supports_image = True
    supports_video = False

    def generate(self, task: Task) -> list[ProviderResultItem]:
        raise NotImplementedError(
            f"[provider={self.name}][stage=generate] not implemented, default model={settings.google_image_model}"
        )

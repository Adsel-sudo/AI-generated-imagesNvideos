from ..config import settings
from ..models import Task
from .base import BaseProvider
from .types import ProviderResultItem


class VeoProvider(BaseProvider):
    """Legacy alias provider for video generation.

    Future plan: route this alias to GoogleVideoProvider implementation.
    """

    name = "veo"
    supports_image = False
    supports_video = True

    def generate(self, task: Task) -> list[ProviderResultItem]:
        raise NotImplementedError(
            f"[provider={self.name}][stage=generate] not implemented, default model={settings.google_video_model}"
        )

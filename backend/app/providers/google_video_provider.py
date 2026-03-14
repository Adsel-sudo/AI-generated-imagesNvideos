from ..config import settings
from ..models import Task
from .base import BaseProvider
from .types import ProviderResultItem


class GoogleVideoProvider(BaseProvider):
    """Skeleton for future Google video backend integration (e.g. Veo)."""

    name = "google_video"
    supports_video = True

    def generate(self, task: Task) -> list[ProviderResultItem]:
        raise NotImplementedError(
            f"[provider={self.name}][stage=generate] model={settings.google_video_model} not implemented"
        )

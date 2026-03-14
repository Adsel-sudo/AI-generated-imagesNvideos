from ..config import settings
from ..models import Task
from .base import BaseProvider
from .types import ProviderResultItem


class GoogleImageProvider(BaseProvider):
    """Skeleton for future Google image backend integration (Gemini image, Imagen, etc.)."""

    name = "google_image"
    supports_image = True

    def generate(self, task: Task) -> list[ProviderResultItem]:
        raise NotImplementedError(
            f"[provider={self.name}][stage=generate] backend={settings.google_image_backend} not implemented"
        )

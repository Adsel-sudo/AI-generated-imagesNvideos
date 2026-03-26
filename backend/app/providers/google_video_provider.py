from collections.abc import Callable

from ..config import settings
from ..models import Task
from ..provider_params import normalize_task_params
from .base import BaseProvider
from .types import ProviderResultItem


class GoogleVideoProvider(BaseProvider):
    """Google video provider skeleton.

    Reserved for follow-up text-to-video and image-to-video integration.
    Planned standardized fields include duration_seconds / fps / extra.
    """

    name = "google_video"
    supports_video = True

    def generate(
        self,
        task: Task,
        on_output: Callable[[ProviderResultItem], None] | None = None,
    ) -> list[ProviderResultItem]:
        params = normalize_task_params(task)
        _ = params  # parsed for future duration/fps/extra mappings.
        _ = on_output

        raise NotImplementedError(
            f"[provider={self.name}][stage=generate] model={settings.google_video_model} not implemented"
        )

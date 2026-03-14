from ..models import Task
from .google_video_provider import GoogleVideoProvider
from .types import ProviderResultItem


class VeoProvider(GoogleVideoProvider):
    """Legacy alias adapter for `provider=veo` requests."""

    name = "veo"

    def generate(self, task: Task) -> list[ProviderResultItem]:
        return GoogleVideoProvider.generate(self, task)

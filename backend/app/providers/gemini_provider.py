from collections.abc import Callable

from ..models import Task
from .google_image_provider import GoogleImageProvider
from .types import ProviderResultItem


class GeminiProvider(GoogleImageProvider):
    """Legacy alias adapter for `provider=gemini` requests."""

    name = "gemini"

    def generate(
        self,
        task: Task,
        on_output: Callable[[ProviderResultItem], None] | None = None,
    ) -> list[ProviderResultItem]:
        return GoogleImageProvider.generate(self, task, on_output=on_output)

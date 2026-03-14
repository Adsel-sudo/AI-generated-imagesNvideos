from ..models import Task
from .base import BaseProvider
from .types import ProviderResultItem


class VeoProvider(BaseProvider):
    name = "veo"
    supports_image = False
    supports_video = True

    def generate(self, task: Task) -> list[ProviderResultItem]:
        raise NotImplementedError("Veo provider is not implemented yet")

from ..config import settings
from ..models import Task
from .base import BaseProvider
from .types import ProviderResultItem


class PromptOptimizerProvider(BaseProvider):
    """Skeleton for prompt optimization workflows.

    Output strategy can evolve to store optimized text in output files or task fields.
    """

    name = "prompt_optimizer"
    supports_prompt = True

    def generate(self, task: Task) -> list[ProviderResultItem]:
        raise NotImplementedError(
            f"[provider={self.name}][stage=generate] model={settings.prompt_optimizer_model} not implemented"
        )

from ..config import settings
from ..models import Task
from ..provider_params import normalize_task_params
from .base import BaseProvider
from .types import ProviderResultItem


class PromptOptimizerProvider(BaseProvider):
    """Simple prompt-optimizer implementation.

    This provider intentionally does not create files. Its main output is task.prompt_final.
    """

    name = "prompt_optimizer"
    supports_prompt = True

    def generate(self, task: Task) -> list[ProviderResultItem]:
        params = normalize_task_params(task)
        style = params.style or "balanced"

        source_text = (task.request_text or "").strip()
        if not source_text:
            raise ValueError(f"[provider={self.name}][stage=generate] request_text is empty")

        task.model_name = settings.prompt_optimizer_model
        task.prompt_final = f"[{style}] {source_text}\n\nHigh quality, detailed, coherent composition."
        return []

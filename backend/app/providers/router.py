from .base import BaseProvider
from .gemini_provider import GeminiProvider
from .google_image_provider import GoogleImageProvider
from .google_video_provider import GoogleVideoProvider
from .mock_provider import MockProvider
from .prompt_optimizer_provider import PromptOptimizerProvider
from .veo_provider import VeoProvider

PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "mock": MockProvider,
    # compatibility aliases
    "gemini": GeminiProvider,
    "veo": VeoProvider,
    # future stable business abstractions
    "google_image": GoogleImageProvider,
    "google_video": GoogleVideoProvider,
    "prompt_optimizer": PromptOptimizerProvider,
}


def get_provider(name: str | None) -> BaseProvider:
    provider_name = (name or "mock").strip().lower()
    provider_cls = PROVIDER_REGISTRY.get(provider_name)
    if provider_cls is None:
        raise ValueError(f"[provider={provider_name}][stage=router] unsupported provider")
    return provider_cls()

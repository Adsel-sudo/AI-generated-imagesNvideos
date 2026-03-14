from .base import BaseProvider
from .gemini_provider import GeminiProvider
from .mock_provider import MockProvider
from .veo_provider import VeoProvider

PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "mock": MockProvider,
    "gemini": GeminiProvider,
    "veo": VeoProvider,
}


def get_provider(name: str | None) -> BaseProvider:
    provider_name = (name or "mock").strip().lower()
    provider_cls = PROVIDER_REGISTRY.get(provider_name)
    if provider_cls is None:
        raise ValueError(f"unsupported provider: {name}")
    return provider_cls()

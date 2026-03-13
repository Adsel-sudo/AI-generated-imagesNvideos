from .base import BaseProvider
from .mock_provider import MockProvider


def get_provider(name: str | None) -> BaseProvider:
    if not name or name == "mock":
        return MockProvider()
    raise ValueError(f"unsupported provider: {name}")

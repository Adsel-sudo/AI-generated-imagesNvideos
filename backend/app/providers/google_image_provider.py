from __future__ import annotations

import mimetypes
import re
from typing import Any

from PIL import Image

from ..config import settings
from ..models import Task
from ..provider_params import normalize_task_params
from ..storage import get_task_output_dir
from .base import BaseProvider
from .types import ProviderResultItem

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:  # noqa: BLE001
    genai = None
    genai_types = None


class GoogleImageProvider(BaseProvider):
    """Google image generation provider using the official google-genai SDK."""

    name = "google_image"
    supports_image = True

    def _api_key(self) -> str:
        api_key = settings.google_genai_api_key or settings.google_api_key
        if not api_key:
            raise ValueError(f"[provider={self.name}][stage=config] missing GOOGLE_GENAI_API_KEY/GOOGLE_API_KEY")
        return api_key

    def _build_prompt(self, task: Task) -> str:
        params = normalize_task_params(task)
        lines = [task.request_text.strip()]
        if params.style:
            lines.append(f"Style: {params.style}")
        if params.negative_prompt:
            lines.append(f"Avoid: {params.negative_prompt}")
        return "\n".join(line for line in lines if line)

    def _normalize_aspect_ratio(self, raw: str | None) -> str | None:
        if not raw:
            return None
        value = raw.strip().lower()
        if re.fullmatch(r"\d+\s*:\s*\d+", value):
            left, _, right = value.partition(":")
            return f"{left.strip()}:{right.strip()}"
        return None

    def _build_config(self, task: Task) -> Any:
        params = normalize_task_params(task)
        extra = dict(params.extra or {})

        response_modalities = ["IMAGE"]
        if genai_types is None:
            return {"response_modalities": response_modalities, "candidate_count": task.n_outputs, **extra}

        cfg: dict[str, Any] = {
            "response_modalities": response_modalities,
            "candidate_count": task.n_outputs,
        }

        if params.seed is not None:
            cfg["seed"] = params.seed

        aspect_ratio = self._normalize_aspect_ratio(params.aspect_ratio)
        if not aspect_ratio:
            aspect_ratio = self._normalize_aspect_ratio(params.size)
        if aspect_ratio:
            cfg["aspect_ratio"] = aspect_ratio

        cfg.update(extra)
        return genai_types.GenerateContentConfig(**cfg)

    def _extract_image_parts(self, response: Any) -> list[tuple[bytes, str]]:
        images: list[tuple[bytes, str]] = []
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                inline_data = getattr(part, "inline_data", None)
                if inline_data and getattr(inline_data, "data", None):
                    mime_type = getattr(inline_data, "mime_type", None) or "image/png"
                    images.append((inline_data.data, mime_type))
        return images

    def generate(self, task: Task) -> list[ProviderResultItem]:
        if genai is None:
            raise RuntimeError(
                f"[provider={self.name}][stage=import] google-genai is not installed or failed to import"
            )

        # Prefer Gemini Developer API (API key auth).
        client = genai.Client(api_key=self._api_key())
        prompt_text = self._build_prompt(task)
        config = self._build_config(task)

        try:
            response = client.models.generate_content(
                model=settings.google_image_model,
                contents=prompt_text,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"[provider={self.name}][stage=generate] {exc}") from exc

        output_dir = get_task_output_dir(task.id)
        output_dir.mkdir(parents=True, exist_ok=True)

        images = self._extract_image_parts(response)
        if not images:
            raise RuntimeError(f"[provider={self.name}][stage=parse_response] no image data returned")

        results: list[ProviderResultItem] = []
        for index, (blob, mime_type) in enumerate(images[: task.n_outputs], start=1):
            ext = mimetypes.guess_extension(mime_type) or ".png"
            file_name = f"output_{index}{ext}"
            file_path = output_dir / file_name
            file_path.write_bytes(blob)

            width = None
            height = None
            try:
                with Image.open(file_path) as image:
                    width, height = image.size
            except Exception:  # noqa: BLE001
                pass

            results.append(
                ProviderResultItem(
                    index=index,
                    file_path=str(file_path),
                    mime_type=mime_type,
                    file_type="image",
                    file_name=file_name,
                    file_size=file_path.stat().st_size,
                    width=width,
                    height=height,
                )
            )

        task.model_name = settings.google_image_model
        task.prompt_final = prompt_text
        return results

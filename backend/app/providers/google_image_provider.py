from __future__ import annotations

import base64
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
        api_key = settings.google_genai_api_key
        if not api_key:
            api_key = settings.google_api_key
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
        if genai_types is None:
            return {}

        params = normalize_task_params(task)
        aspect_ratio = self._normalize_aspect_ratio(params.aspect_ratio)
        if not aspect_ratio:
            aspect_ratio = self._normalize_aspect_ratio(params.size)

        if aspect_ratio:
            image_config = genai_types.ImageConfig(aspect_ratio=aspect_ratio)
            return genai_types.GenerateContentConfig(image_config=image_config)

        return genai_types.GenerateContentConfig()

    def _extract_response_parts(self, response: Any) -> list[Any]:
        parts = getattr(response, "parts", None) or []
        if parts:
            return list(parts)

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            candidate_parts = getattr(content, "parts", None) or []
            if candidate_parts:
                return list(candidate_parts)
        return []

    def _save_part_image(self, part: Any, file_path: Any) -> tuple[str, bool]:
        mime_type = "image/png"

        as_image = getattr(part, "as_image", None)
        if callable(as_image):
            try:
                image_obj = as_image()
                image_obj.save(file_path)
                image_format = getattr(image_obj, "format", None)
                if image_format:
                    guessed = mimetypes.types_map.get(f".{image_format.lower()}")
                    if guessed:
                        mime_type = guessed
                return mime_type, True
            except Exception:  # noqa: BLE001
                pass

        inline_data = getattr(part, "inline_data", None)
        data = getattr(inline_data, "data", None)
        if not data:
            return mime_type, False

        mime_type = getattr(inline_data, "mime_type", None) or mime_type

        if isinstance(data, bytes):
            file_path.write_bytes(data)
            return mime_type, True

        if isinstance(data, str):
            decoded = base64.b64decode(data)
            file_path.write_bytes(decoded)
            return mime_type, True

        return mime_type, False

    def generate(self, task: Task) -> list[ProviderResultItem]:
        if genai is None:
            raise RuntimeError(
                f"[provider={self.name}][stage=import] google-genai is not installed or failed to import"
            )

        client = genai.Client(api_key=self._api_key())
        prompt_text = self._build_prompt(task)
        config = self._build_config(task)

        try:
            response = client.models.generate_content(
                model=settings.google_image_model,
                contents=[prompt_text],
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"[provider={self.name}][stage=generate] [{type(exc).__name__}] {exc!r}") from exc

        output_dir = get_task_output_dir(task.id)
        output_dir.mkdir(parents=True, exist_ok=True)

        parts = self._extract_response_parts(response)

        results: list[ProviderResultItem] = []
        for part in parts:
            if len(results) >= task.n_outputs:
                break

            index = len(results) + 1
            inline_data = getattr(part, "inline_data", None)
            initial_mime_type = getattr(inline_data, "mime_type", None) or "image/png"
            ext = mimetypes.guess_extension(initial_mime_type) or ".png"

            file_name = f"output_{index}{ext}"
            file_path = output_dir / file_name

            mime_type, saved = self._save_part_image(part, file_path)
            if not saved:
                continue

            final_ext = mimetypes.guess_extension(mime_type) or ext or ".png"
            if final_ext != file_path.suffix:
                final_name = f"output_{index}{final_ext}"
                final_path = output_dir / final_name
                file_path.rename(final_path)
                file_path = final_path
                file_name = final_name

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

        if not results:
            raise RuntimeError(f"[provider={self.name}][stage=parse_response] no image data returned")

        task.model_name = settings.google_image_model
        task.prompt_final = prompt_text
        return results

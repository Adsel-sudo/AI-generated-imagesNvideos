from __future__ import annotations

import base64
import math
import logging
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

logger = logging.getLogger(__name__)


def _safe_getattr(obj: Any, attr: str, default: Any = None) -> Any:
    try:
        return getattr(obj, attr, default)
    except Exception:  # noqa: BLE001
        return default


class GoogleImageProvider(BaseProvider):
    """Google image generation provider using the official google-genai SDK."""

    name = "google_image"
    supports_image = True

    def _api_key(self) -> str:
        api_key = settings.google_genai_api_key
        if not api_key:
            api_key = settings.google_api_key
        api_key = (api_key or "").replace("\ufeff", "").strip()
        if not api_key:
            raise ValueError(f"[provider={self.name}][stage=config] missing GOOGLE_GENAI_API_KEY/GOOGLE_API_KEY")
        return api_key

    def _build_prompt(self, task: Task) -> str:
        params = normalize_task_params(task)
        params_extra = params.extra if isinstance(params.extra, dict) else {}
        current_target = params_extra.get("current_target") if isinstance(params_extra.get("current_target"), dict) else {}
        references = params_extra.get("references") if isinstance(params_extra.get("references"), list) else []

        primary_text = (task.prompt_final or task.request_text or "").strip()
        lines = [primary_text] if primary_text else []

        target_width = current_target.get("width") or params.width
        target_height = current_target.get("height") or params.height
        target_aspect_ratio = current_target.get("aspect_ratio") or params.aspect_ratio

        if target_width and target_height:
            lines.append(f"Target resolution preference: {target_width}x{target_height}px")
        elif params.size:
            lines.append(f"Target resolution preference: {params.size}")

        if target_aspect_ratio:
            lines.append(f"Target aspect ratio: {target_aspect_ratio}")
        if params.style:
            lines.append(f"Style: {params.style}")
        if params.negative_prompt:
            lines.append(f"Avoid: {params.negative_prompt}")
        if references:
            role_count: dict[str, int] = {}
            for item in references:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "reference").strip().lower()
                role_count[role] = role_count.get(role, 0) + 1
            if role_count.get("product"):
                lines.append(
                    f"Product references: {role_count['product']} image(s); keep subject identity and key details consistent."
                )
            if role_count.get("composition"):
                lines.append(
                    f"Composition references: {role_count['composition']} image(s); follow scene layout/background relations and only change user-requested parts."
                )
            if role_count.get("pose"):
                lines.append(f"Pose references: {role_count['pose']} image(s); align subject pose.")
            if role_count.get("style"):
                lines.append(f"Style references: {role_count['style']} image(s); align color/light/material style.")
            other_count = role_count.get("reference", 0)
            if other_count:
                lines.append(f"Other references: {other_count} image(s); keep semantic consistency.")
        lines.append("Prioritize matching requested size/aspect ratio while keeping main subject complete and sharp.")
        return "\n".join(line for line in lines if line)

    def _normalize_aspect_ratio(self, raw: str | None) -> str | None:
        if not raw:
            return None
        value = raw.strip().lower()
        if re.fullmatch(r"\d+\s*:\s*\d+", value):
            left, _, right = value.partition(":")
            return f"{left.strip()}:{right.strip()}"
        if re.fullmatch(r"\d+\s*x\s*\d+", value):
            left, _, right = value.partition("x")
            try:
                width = int(left.strip())
                height = int(right.strip())
            except ValueError:
                return None
            if width <= 0 or height <= 0:
                return None
            ratio_gcd = math.gcd(width, height)
            return f"{width // ratio_gcd}:{height // ratio_gcd}"
        return None

    def _build_config(self, task: Task) -> Any:
        if genai_types is None:
            return {}

        params = normalize_task_params(task)
        current_target = params.extra.get("current_target") if isinstance(params.extra, dict) else None
        target_aspect_ratio = current_target.get("aspect_ratio") if isinstance(current_target, dict) else None
        target_width = current_target.get("width") if isinstance(current_target, dict) else None
        target_height = current_target.get("height") if isinstance(current_target, dict) else None
        aspect_ratio = self._normalize_aspect_ratio(target_aspect_ratio or params.aspect_ratio)
        if not aspect_ratio and isinstance(target_width, int) and isinstance(target_height, int) and target_width > 0 and target_height > 0:
            aspect_ratio = self._normalize_aspect_ratio(f"{target_width}x{target_height}")
        if not aspect_ratio and isinstance(params.width, int) and isinstance(params.height, int) and params.width > 0 and params.height > 0:
            aspect_ratio = self._normalize_aspect_ratio(f"{params.width}x{params.height}")
        if not aspect_ratio:
            aspect_ratio = self._normalize_aspect_ratio(params.size)

        if aspect_ratio:
            image_config = genai_types.ImageConfig(aspect_ratio=aspect_ratio)
            return genai_types.GenerateContentConfig(image_config=image_config)

        return genai_types.GenerateContentConfig()

    def _extract_response_parts(self, response: Any) -> list[Any]:
        parts = _safe_getattr(response, "parts", None) or []
        if parts:
            return list(parts)

        candidates = _safe_getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = _safe_getattr(candidate, "content", None)
            candidate_parts = _safe_getattr(content, "parts", None) or []
            if candidate_parts:
                return list(candidate_parts)
        return []

    def _save_part_image(self, part: Any, file_path: Any) -> tuple[str, bool]:
        mime_type = "image/png"

        as_image = _safe_getattr(part, "as_image", None)
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

        inline_data = _safe_getattr(part, "inline_data", None)
        data = _safe_getattr(inline_data, "data", None)
        if not data:
            return mime_type, False

        mime_type = _safe_getattr(inline_data, "mime_type", None) or mime_type

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
        model_name = (settings.google_image_model or "").strip()

        if not model_name:
            raise ValueError(f"[provider={self.name}][stage=config] missing GOOGLE_IMAGE_MODEL")

        output_dir = get_task_output_dir(task.id)
        output_dir.mkdir(parents=True, exist_ok=True)

        results: list[ProviderResultItem] = []
        max_attempts = max(1, task.n_outputs)
        for attempt in range(max_attempts):
            if len(results) >= task.n_outputs:
                break

            logger.info(
                "[provider=%s][stage=generate] model=%s attempt=%s/%s target_outputs=%s current_outputs=%s",
                self.name,
                model_name,
                attempt + 1,
                max_attempts,
                task.n_outputs,
                len(results),
            )
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[prompt_text],
                    config=config,
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"[provider={self.name}][stage=generate][model={model_name}] "
                    f"[{type(exc).__name__}] {exc!r}"
                ) from exc

            try:
                parts = self._extract_response_parts(response)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"[provider={self.name}][stage=parse_response][model={model_name}] "
                    f"failed to read response parts: {type(exc).__name__}"
                ) from exc

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
            raise RuntimeError(
                f"[provider={self.name}][stage=parse_response][model={model_name}] no image data returned"
            )

        task.model_name = model_name
        task.prompt_final = prompt_text
        logger.info(
            "[provider=%s][stage=done] model=%s generated=%s",
            self.name,
            model_name,
            len(results),
        )
        return results

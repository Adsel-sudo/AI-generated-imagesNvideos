from __future__ import annotations

import base64
import logging
import math
import mimetypes
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

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

_ROLE_HINTS = {
    "product": "Keep product identity, shape, and key details consistent with this reference.",
    "composition": "Follow the scene composition/layout and background relationship from this reference.",
    "pose": "Align subject pose and body arrangement with this reference.",
    "style": "Align color palette, lighting, and material/rendering style with this reference.",
    "reference": "Use this as a general semantic reference.",
}


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

    def _get_references(self, task: Task) -> list[dict[str, Any]]:
        params = normalize_task_params(task)
        params_extra = params.extra if isinstance(params.extra, dict) else {}
        references = params_extra.get("references")
        if not isinstance(references, list):
            return []
        return [item for item in references if isinstance(item, dict)]

    def _build_prompt(self, task: Task) -> str:
        params = normalize_task_params(task)
        params_extra = params.extra if isinstance(params.extra, dict) else {}
        current_target = params_extra.get("current_target") if isinstance(params_extra.get("current_target"), dict) else {}
        references = self._get_references(task)

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

    def _resolve_reference_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return Path.cwd() / path

    def _build_multimodal_contents(self, task: Task, prompt_text: str) -> list[Any]:
        contents: list[Any] = [prompt_text]
        references = self._get_references(task)
        if not references:
            return contents

        if genai_types is None or not hasattr(genai_types, "Part"):
            logger.warning(
                "[provider=%s][stage=references] google-genai types.Part unavailable; falling back to prompt-only references",
                self.name,
            )
            return contents

        attached_count = 0
        for idx, item in enumerate(references, start=1):
            role = str(item.get("role") or "reference").strip().lower()
            role_hint = _ROLE_HINTS.get(role, _ROLE_HINTS["reference"])
            raw_path = item.get("file_path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                logger.warning(
                    "[provider=%s][stage=references] skip reference #%s due to invalid file_path: %r",
                    self.name,
                    idx,
                    raw_path,
                )
                continue

            ref_path = self._resolve_reference_path(raw_path.strip())
            if not ref_path.exists() or not ref_path.is_file():
                logger.warning(
                    "[provider=%s][stage=references] reference file not found: %s",
                    self.name,
                    ref_path,
                )
                continue

            try:
                data = ref_path.read_bytes()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[provider=%s][stage=references] failed reading reference file=%s err=%s",
                    self.name,
                    ref_path,
                    exc,
                )
                continue

            mime_type = mimetypes.guess_type(ref_path.name)[0] or "image/png"
            if not mime_type.startswith("image/"):
                logger.warning(
                    "[provider=%s][stage=references] unsupported mime=%s for file=%s, trying image/jpeg fallback",
                    self.name,
                    mime_type,
                    ref_path,
                )
                mime_type = "image/jpeg"

            contents.append(f"Reference #{idx} role={role}: {role_hint}")

            part_obj = None
            try:
                part_obj = genai_types.Part.from_bytes(data=data, mime_type=mime_type)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[provider=%s][stage=references] Part.from_bytes failed for file=%s role=%s mime=%s err=%s; trying PIL fallback",
                    self.name,
                    ref_path,
                    role,
                    mime_type,
                    exc,
                )

            if part_obj is not None:
                contents.append(part_obj)
                attached_count += 1
                continue

            try:
                with Image.open(ref_path) as image:
                    contents.append(image.copy())
                    attached_count += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[provider=%s][stage=references] PIL fallback failed for file=%s role=%s err=%s",
                    self.name,
                    ref_path,
                    role,
                    exc,
                )

        logger.info(
            "[provider=%s][stage=references] total=%s attached=%s",
            self.name,
            len(references),
            attached_count,
        )
        return contents

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

    def _count_runs(self, values: list[float], threshold: float, min_run: int, margin: int) -> int:
        runs = 0
        run_start = -1
        for index, value in enumerate(values):
            if value >= threshold:
                if run_start < 0:
                    run_start = index
                continue
            if run_start >= 0:
                run_end = index - 1
                if run_end - run_start + 1 >= min_run and run_start >= margin and run_end <= len(values) - margin - 1:
                    runs += 1
                run_start = -1
        if run_start >= 0:
            run_end = len(values) - 1
            if run_end - run_start + 1 >= min_run and run_start >= margin and run_end <= len(values) - margin - 1:
                runs += 1
        return runs

    def _detect_collage_layout(self, image_path: Path, expected_outputs: int) -> tuple[bool, dict[str, Any]]:
        if expected_outputs <= 1:
            return False, {"reason": "single_output"}

        with Image.open(image_path) as image:
            gray = image.convert("L")
            gray.thumbnail((640, 640))
            width, height = gray.size
            if width < 96 or height < 96:
                return False, {"reason": "image_too_small", "width": width, "height": height}

            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_pixels = edges.load()
            gray_pixels = gray.load()
            stride = 2
            sample_rows = max(1, len(range(0, height, stride)))
            sample_cols = max(1, len(range(0, width, stride)))

            vertical_density: list[float] = []
            for x in range(width):
                count = 0
                for y in range(0, height, stride):
                    if edge_pixels[x, y] >= 90:
                        count += 1
                vertical_density.append(count / sample_rows)

            horizontal_density: list[float] = []
            for y in range(height):
                count = 0
                for x in range(0, width, stride):
                    if edge_pixels[x, y] >= 90:
                        count += 1
                horizontal_density.append(count / sample_cols)

            margin_x = max(3, int(width * 0.05))
            margin_y = max(3, int(height * 0.05))
            min_run_x = max(2, width // 150)
            min_run_y = max(2, height // 150)

            vertical_split_runs = self._count_runs(vertical_density, threshold=0.56, min_run=min_run_x, margin=margin_x)
            horizontal_split_runs = self._count_runs(horizontal_density, threshold=0.56, min_run=min_run_y, margin=margin_y)

            bright_or_dark_uniform_cols: list[float] = []
            for x in range(width):
                values = [gray_pixels[x, y] for y in range(0, height, stride)]
                mean_val = sum(values) / len(values)
                if 18 <= mean_val <= 237:
                    bright_or_dark_uniform_cols.append(0.0)
                    continue
                std_val = ImageStat.Stat(Image.new("L", (1, len(values)), bytes(values))).stddev[0]
                bright_or_dark_uniform_cols.append(1.0 if std_val <= 10.0 else 0.0)

            bright_or_dark_uniform_rows: list[float] = []
            for y in range(height):
                values = [gray_pixels[x, y] for x in range(0, width, stride)]
                mean_val = sum(values) / len(values)
                if 18 <= mean_val <= 237:
                    bright_or_dark_uniform_rows.append(0.0)
                    continue
                std_val = ImageStat.Stat(Image.new("L", (len(values), 1), bytes(values))).stddev[0]
                bright_or_dark_uniform_rows.append(1.0 if std_val <= 10.0 else 0.0)

            vertical_gutter_runs = self._count_runs(bright_or_dark_uniform_cols, threshold=1.0, min_run=min_run_x, margin=margin_x)
            horizontal_gutter_runs = self._count_runs(bright_or_dark_uniform_rows, threshold=1.0, min_run=min_run_y, margin=margin_y)

            has_grid = vertical_split_runs >= 1 and horizontal_split_runs >= 1
            has_multi_split = vertical_split_runs >= 2 or horizontal_split_runs >= 2
            has_uniform_gutter = vertical_gutter_runs >= 1 or horizontal_gutter_runs >= 1

            detected = has_grid or (has_multi_split and has_uniform_gutter)
            metrics = {
                "width": width,
                "height": height,
                "vertical_split_runs": vertical_split_runs,
                "horizontal_split_runs": horizontal_split_runs,
                "vertical_gutter_runs": vertical_gutter_runs,
                "horizontal_gutter_runs": horizontal_gutter_runs,
                "has_grid": has_grid,
                "has_multi_split": has_multi_split,
                "has_uniform_gutter": has_uniform_gutter,
            }
            return detected, metrics

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

    def generate(
        self,
        task: Task,
        on_output: Callable[[ProviderResultItem], None] | None = None,
    ) -> list[ProviderResultItem]:
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
        max_attempts = max(1, task.n_outputs * settings.google_image_max_attempts_multiplier)
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
            request_contents = self._build_multimodal_contents(task, prompt_text)
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=request_contents,
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

                if settings.google_image_collage_guard_enabled:
                    try:
                        is_collage, collage_metrics = self._detect_collage_layout(file_path, task.n_outputs)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "[provider=%s][stage=collage_guard] detect_failed file=%s err=%s",
                            self.name,
                            file_path,
                            exc,
                        )
                        is_collage = False
                        collage_metrics = {"detect_error": str(exc)}

                    if is_collage:
                        logger.warning(
                            "[provider=%s][stage=collage_guard] detected_collage=%s retry_on_collage=%s file=%s metrics=%s",
                            self.name,
                            is_collage,
                            settings.google_image_retry_on_collage,
                            file_path,
                            collage_metrics,
                        )
                        if settings.google_image_retry_on_collage:
                            try:
                                file_path.unlink(missing_ok=True)
                            except Exception:  # noqa: BLE001
                                pass
                            continue

                output_item = ProviderResultItem(
                    index=index,
                    file_path=str(file_path),
                    mime_type=mime_type,
                    file_type="image",
                    file_name=file_name,
                    file_size=file_path.stat().st_size,
                    width=width,
                    height=height,
                )
                results.append(output_item)
                if on_output:
                    on_output(output_item)

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

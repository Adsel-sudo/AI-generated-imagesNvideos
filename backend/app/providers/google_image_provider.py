from __future__ import annotations

import base64
import concurrent.futures
import io
import logging
import math
import mimetypes
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat
from sqlmodel import Session, select

from ..config import settings
from ..db import engine
from ..enums import TaskStatus
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


class GenerateContentCallError(RuntimeError):
    def __init__(self, error_type: str, index: int, original: Exception):
        super().__init__(str(original))
        self.error_type = error_type
        self.index = index
        self.original = original


class GenerateContentTimeoutError(TimeoutError):
    """Raised when generate_content exceeds configured timeout."""


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

    def _normalize_resolution(self, raw: Any) -> str:
        if isinstance(raw, str):
            normalized = raw.strip().upper()
            if normalized in {"2K", "4K"}:
                return normalized
        return "2K"

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

        image_size = self._normalize_resolution(params.resolution)
        image_config_kwargs: dict[str, Any] = {"image_size": image_size}
        if aspect_ratio:
            image_config_kwargs["aspect_ratio"] = aspect_ratio

        image_config = genai_types.ImageConfig(**image_config_kwargs)
        logger.info(
            "[provider=%s][stage=config] task_id=%s aspect_ratio=%s image_size=%s",
            self.name,
            task.id,
            aspect_ratio,
            image_size,
        )
        return genai_types.GenerateContentConfig(image_config=image_config)

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

            prepared_data, prepared_mime_type = self._prepare_reference_payload(
                task_id=str(task.id),
                index=idx,
                role=role,
                raw_data=data,
                raw_mime_type=mime_type,
            )

            contents.append(f"Reference #{idx} role={role}: {role_hint}")

            part_obj = None
            try:
                part_obj = genai_types.Part.from_bytes(data=prepared_data, mime_type=prepared_mime_type)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[provider=%s][stage=references] Part.from_bytes failed for file=%s role=%s mime=%s err=%s; trying PIL fallback",
                    self.name,
                    ref_path,
                    role,
                    prepared_mime_type,
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

    def _format_bytes(self, size: int) -> str:
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}MB"
        if size >= 1024:
            return f"{size / 1024:.1f}KB"
        return f"{size}B"

    def _prepare_reference_payload(
        self,
        *,
        task_id: str,
        index: int,
        role: str,
        raw_data: bytes,
        raw_mime_type: str,
    ) -> tuple[bytes, str]:
        if not settings.google_image_reference_convert_enabled:
            return raw_data, raw_mime_type

        start_ts = time.perf_counter()
        orig_bytes = len(raw_data)
        fallback_dims = "unknown"

        try:
            with Image.open(io.BytesIO(raw_data)) as source_img:
                orig_width, orig_height = source_img.size
                fallback_dims = f"{orig_width}x{orig_height}"
                max_edge = max(1, settings.google_image_reference_max_edge)
                longest = max(orig_width, orig_height)
                if longest > max_edge:
                    scale = max_edge / float(longest)
                    resized_width = max(1, int(round(orig_width * scale)))
                    resized_height = max(1, int(round(orig_height * scale)))
                    resample = getattr(Image, "Resampling", Image).LANCZOS
                    processed_img = source_img.resize((resized_width, resized_height), resample=resample)
                else:
                    resized_width, resized_height = orig_width, orig_height
                    processed_img = source_img.copy()

            rgb_img = processed_img.convert("RGB")
            output = io.BytesIO()
            rgb_img.save(
                output,
                format="JPEG",
                quality=settings.google_image_reference_jpeg_quality,
                optimize=True,
            )
            prepared_data = output.getvalue()
            duration = time.perf_counter() - start_ts
            logger.info(
                "[provider=%s][stage=reference_prepare][task_id=%s][index=%s][role=%s][orig=%sx%s][orig_bytes=%s][new=%sx%s][new_bytes=%s][duration=%.2fs]",
                self.name,
                task_id,
                index,
                role,
                orig_width,
                orig_height,
                self._format_bytes(orig_bytes),
                resized_width,
                resized_height,
                self._format_bytes(len(prepared_data)),
                duration,
            )
            return prepared_data, "image/jpeg"
        except Exception as exc:  # noqa: BLE001
            duration = time.perf_counter() - start_ts
            logger.warning(
                "[provider=%s][stage=reference_prepare_fallback][task_id=%s][index=%s][role=%s][orig=%s][orig_bytes=%s][duration=%.2fs][error_class=%s] %s",
                self.name,
                task_id,
                index,
                role,
                fallback_dims,
                self._format_bytes(orig_bytes),
                duration,
                type(exc).__name__,
                exc,
            )
            return raw_data, raw_mime_type

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
        guard_start = time.perf_counter()
        logger.info(
            "[provider=%s][stage=collage_guard_start][image_path=%s][expected_outputs=%s]",
            self.name,
            image_path,
            expected_outputs,
        )
        if expected_outputs <= 1:
            duration = time.perf_counter() - guard_start
            logger.info(
                "[provider=%s][stage=collage_guard_done][image_path=%s][detected=%s][reason=single_output][duration=%.2fs]",
                self.name,
                image_path,
                False,
                duration,
            )
            return False, {"reason": "single_output"}

        with Image.open(image_path) as image:
            gray = image.convert("L")
            gray.thumbnail((640, 640))
            width, height = gray.size
            if width < 96 or height < 96:
                duration = time.perf_counter() - guard_start
                logger.info(
                    "[provider=%s][stage=collage_guard_done][image_path=%s][detected=%s][reason=image_too_small][duration=%.2fs]",
                    self.name,
                    image_path,
                    False,
                    duration,
                )
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
            duration = time.perf_counter() - guard_start
            logger.info(
                "[provider=%s][stage=collage_guard_done][image_path=%s][detected=%s][duration=%.2fs]",
                self.name,
                image_path,
                detected,
                duration,
            )
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

    def _is_task_cancelled(self, task_id: str) -> bool:
        with Session(engine) as session:
            status = session.exec(select(Task.status).where(Task.id == task_id)).one_or_none()
        return status == TaskStatus.CANCELLED.value

    def _classify_generate_exception(self, exc: Exception) -> str:
        name = type(exc).__name__.lower()
        message = str(exc).lower()
        combined = f"{name} {message}"

        network_markers = (
            "remoteprotocolerror",
            "readtimeout",
            "connecttimeout",
            "timeout",
            "connecterror",
            "networkerror",
            "transporterror",
            "server disconnected",
            "connection reset",
            "temporarily unavailable",
            "service unavailable",
            "too many requests",
            "rate limit",
            "eof",
        )
        if any(marker in combined for marker in network_markers):
            return "retryable_network_error"

        parameter_markers = (
            "invalidargument",
            "badrequest",
            "validation",
            "invalid value",
            "unsupported",
            "malformed",
            "missing required",
            "permission denied",
            "unauthorized",
            "forbidden",
        )
        if isinstance(exc, (ValueError, TypeError)) or any(marker in combined for marker in parameter_markers):
            return "parameter_error"

        return "model_response_error"

    def _generate_content_with_retry(
        self,
        *,
        client: Any,
        model_name: str,
        request_contents: list[Any],
        config: Any,
        task_id: str,
        index: int,
        resolution: str,
        aspect_ratio: str | None,
        references_count: int,
        max_retries: int = 3,
    ) -> Any:
        timeout_seconds = settings.google_image_generate_timeout_seconds
        for retry in range(max_retries):
            attempt = retry + 1
            start_ts = time.perf_counter()
            logger.info(
                "[provider=%s][stage=generate_content_start][task_id=%s][attempt=%s][model=%s][resolution=%s][image_size=%s][aspect_ratio=%s][refs=%s]",
                self.name,
                task_id,
                attempt,
                model_name,
                resolution,
                resolution,
                aspect_ratio or "unknown",
                references_count,
            )
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        client.models.generate_content,
                        model=model_name,
                        contents=request_contents,
                        config=config,
                    )
                    response = future.result(timeout=timeout_seconds)
                duration = time.perf_counter() - start_ts
                logger.info(
                    "[provider=%s][stage=generate_content_done][task_id=%s][attempt=%s][duration=%.2fs]",
                    self.name,
                    task_id,
                    attempt,
                    duration,
                )
                return response
            except concurrent.futures.TimeoutError:
                duration = time.perf_counter() - start_ts
                exc = GenerateContentTimeoutError(
                    f"generate_content timed out after {timeout_seconds}s"
                )
                logger.warning(
                    "[provider=%s][stage=generate_content_timeout][task_id=%s][attempt=%s][timeout_seconds=%s][duration=%.2fs][error_class=%s] %s",
                    self.name,
                    task_id,
                    attempt,
                    timeout_seconds,
                    duration,
                    type(exc).__name__,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001
                duration = time.perf_counter() - start_ts
                error_type = self._classify_generate_exception(exc)
                logger.warning(
                    "[provider=%s][stage=generate_content_error][task_id=%s][index=%s][attempt=%s/%s][duration=%.2fs][error_type=%s][error_class=%s] %s",
                    self.name,
                    task_id,
                    index,
                    attempt,
                    max_retries,
                    duration,
                    error_type,
                    type(exc).__name__,
                    exc,
                )
                if error_type == "retryable_network_error" and retry + 1 < max_retries:
                    time.sleep(min(2**retry, 4))
                    continue
                raise GenerateContentCallError(error_type=error_type, index=index, original=exc) from exc

            error_type = self._classify_generate_exception(exc)
            logger.warning(
                "[provider=%s][stage=generate_content_error][task_id=%s][index=%s][attempt=%s/%s][error_type=%s][error_class=%s] %s",
                self.name,
                task_id,
                index,
                attempt,
                max_retries,
                error_type,
                type(exc).__name__,
                exc,
            )
            if error_type == "retryable_network_error" and retry + 1 < max_retries:
                time.sleep(min(2**retry, 4))
                continue
            raise GenerateContentCallError(error_type=error_type, index=index, original=exc) from exc

        raise GenerateContentCallError(
            error_type="retryable_network_error",
            index=index,
            original=RuntimeError("generate_content exhausted retries without response"),
        )

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
        last_error_detail: str | None = None
        references = self._get_references(task)
        build_refs_start = time.perf_counter()
        logger.info(
            "[provider=%s][stage=build_references_start][task_id=%s][refs=%s]",
            self.name,
            task.id,
            len(references),
        )
        request_contents = self._build_multimodal_contents(task, prompt_text)
        build_refs_duration = time.perf_counter() - build_refs_start
        logger.info(
            "[provider=%s][stage=build_references_done][task_id=%s][refs=%s][duration=%.2fs]",
            self.name,
            task.id,
            len(references),
            build_refs_duration,
        )
        image_config = _safe_getattr(config, "image_config", None)
        image_size = _safe_getattr(image_config, "image_size", None) or self._normalize_resolution(
            normalize_task_params(task).resolution
        )
        aspect_ratio = _safe_getattr(image_config, "aspect_ratio", None)
        for attempt in range(max_attempts):
            if len(results) >= task.n_outputs:
                break

            current_index = len(results) + 1
            if self._is_task_cancelled(str(task.id)):
                logger.info(
                    "[provider=%s][stage=cancelled][task_id=%s][index=%s] stop generating due to cancel request",
                    self.name,
                    task.id,
                    current_index,
                )
                break

            logger.info(
                "[provider=%s][stage=generate][task_id=%s][index=%s] model=%s attempt=%s/%s target_outputs=%s current_outputs=%s",
                self.name,
                task.id,
                current_index,
                model_name,
                attempt + 1,
                max_attempts,
                task.n_outputs,
                len(results),
            )
            try:
                response = self._generate_content_with_retry(
                    client=client,
                    model_name=model_name,
                    request_contents=request_contents,
                    config=config,
                    task_id=str(task.id),
                    index=current_index,
                    resolution=image_size,
                    aspect_ratio=aspect_ratio,
                    references_count=len(references),
                )
            except GenerateContentCallError as exc:
                last_error_detail = (
                    f"[{exc.error_type}][index={exc.index}][class={type(exc.original).__name__}] {exc.original}"
                )
                if exc.error_type == "parameter_error":
                    raise RuntimeError(
                        f"[provider={self.name}][stage=generate][task_id={task.id}][model={model_name}] {last_error_detail}"
                    ) from exc
                continue

            try:
                parts = self._extract_response_parts(response)
            except Exception as exc:  # noqa: BLE001
                error_type = "model_response_error"
                last_error_detail = f"[{error_type}][index={current_index}][class={type(exc).__name__}] {exc}"
                logger.warning(
                    "[provider=%s][stage=parse_response][task_id=%s][index=%s][error_type=%s][error_class=%s] %s",
                    self.name,
                    task.id,
                    current_index,
                    error_type,
                    type(exc).__name__,
                    exc,
                )
                continue

            if not parts:
                last_error_detail = f"[model_response_error][index={current_index}] empty_parts"
                logger.warning(
                    "[provider=%s][stage=parse_response][task_id=%s][index=%s][error_type=model_response_error] empty image parts",
                    self.name,
                    task.id,
                    current_index,
                )
                continue

            for part in parts:
                if len(results) >= task.n_outputs:
                    break

                index = len(results) + 1
                inline_data = getattr(part, "inline_data", None)
                initial_mime_type = getattr(inline_data, "mime_type", None) or "image/png"
                ext = mimetypes.guess_extension(initial_mime_type) or ".png"

                file_name = f"output_{index}{ext}"
                file_path = output_dir / file_name

                save_start = time.perf_counter()
                logger.info(
                    "[provider=%s][stage=save_image_start][task_id=%s][index=%s][path=%s]",
                    self.name,
                    task.id,
                    index,
                    file_path,
                )
                mime_type, saved = self._save_part_image(part, file_path)
                save_duration = time.perf_counter() - save_start
                logger.info(
                    "[provider=%s][stage=save_image_done][task_id=%s][index=%s][path=%s][saved=%s][duration=%.2fs]",
                    self.name,
                    task.id,
                    index,
                    file_path,
                    saved,
                    save_duration,
                )
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
                logger.info(
                    "[provider=%s][stage=append_result_start][task_id=%s][index=%s][path=%s]",
                    self.name,
                    task.id,
                    index,
                    file_path,
                )
                results.append(output_item)
                logger.info(
                    "[provider=%s][stage=append_result_done][task_id=%s][index=%s][path=%s]",
                    self.name,
                    task.id,
                    index,
                    file_path,
                )
                if on_output:
                    logger.info(
                        "[provider=%s][stage=on_output_start][task_id=%s][index=%s]",
                        self.name,
                        task.id,
                        index,
                    )
                    on_output(output_item)
                    logger.info(
                        "[provider=%s][stage=on_output_done][task_id=%s][index=%s]",
                        self.name,
                        task.id,
                        index,
                    )

        if not results:
            raise RuntimeError(
                f"[provider={self.name}][stage=parse_response][task_id={task.id}][model={model_name}] no image data returned"
                + (f"; last_error={last_error_detail}" if last_error_detail else "")
            )
        if len(results) < task.n_outputs:
            logger.warning(
                "[provider=%s][stage=partial_success][task_id=%s] generated=%s requested=%s last_error=%s",
                self.name,
                task.id,
                len(results),
                task.n_outputs,
                last_error_detail,
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

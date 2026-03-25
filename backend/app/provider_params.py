import json
from typing import Any

from .models import Task
from .schemas import StandardTaskParams

STANDARD_PARAM_KEYS = {
    "size",
    "width",
    "height",
    "aspect_ratio",
    "style",
    "seed",
    "negative_prompt",
    "duration_seconds",
    "fps",
    "extra",
}


def normalize_task_params(task: Task) -> StandardTaskParams:
    """Build normalized params from task.params_json with compatibility fallbacks."""
    raw: dict[str, Any] = {}
    if task.params_json:
        try:
            parsed = json.loads(task.params_json)
            if isinstance(parsed, dict):
                raw = parsed
        except (TypeError, ValueError, json.JSONDecodeError):
            raw = {}

    if not isinstance(raw, dict):
        return StandardTaskParams()

    base: dict[str, Any] = {k: raw.get(k) for k in STANDARD_PARAM_KEYS if k in raw and k != "extra"}
    usage_options = raw.get("usage_options") if isinstance(raw.get("usage_options"), dict) else {}
    if base.get("size") is None and isinstance(usage_options.get("size"), str):
        base["size"] = usage_options.get("size")
    if base.get("style") is None and isinstance(usage_options.get("style_preference"), str):
        base["style"] = usage_options.get("style_preference")

    # Allow width/height derived from `size` forms like "1024x1024".
    size = raw.get("size")
    if not isinstance(size, str):
        size = base.get("size")
    if isinstance(size, str) and "x" in size and (base.get("width") is None or base.get("height") is None):
        left, _, right = size.lower().partition("x")
        try:
            base.setdefault("width", int(left.strip()))
            base.setdefault("height", int(right.strip()))
        except ValueError:
            pass

    extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
    # Put all unknown keys in extra so legacy/new provider-specific arguments are not lost.
    for key, value in raw.items():
        if key not in STANDARD_PARAM_KEYS:
            extra[key] = value

    base["extra"] = extra
    return StandardTaskParams.model_validate(base)

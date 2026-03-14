from typing import Any

from .models import Task
from .providers.utils import load_task_params
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
    """Build normalized params from legacy task.params_json with compatibility fallbacks."""
    raw = load_task_params(task)
    if not isinstance(raw, dict):
        return StandardTaskParams()

    base: dict[str, Any] = {k: raw.get(k) for k in STANDARD_PARAM_KEYS if k in raw and k != "extra"}

    # Allow width/height derived from `size` forms like "1024x1024".
    size = raw.get("size")
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

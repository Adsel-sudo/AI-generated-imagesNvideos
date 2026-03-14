import json

from ..models import Task


def load_task_params(task: Task) -> dict:
    if not task.params_json:
        return {}

    try:
        parsed = json.loads(task.params_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}

    if isinstance(parsed, dict):
        return parsed

    return {}

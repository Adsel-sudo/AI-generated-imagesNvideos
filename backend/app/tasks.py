import json
import logging
from copy import deepcopy
from typing import Any

from sqlmodel import Session, select

from .celery_app import celery_app
from .db import engine
from .enums import TaskStatus, TaskType
from .models import Output, Task, utcnow
from .config import settings
from .providers.router import get_provider

logger = logging.getLogger(__name__)


def _update_task_status(
    session: Session,
    task: Task,
    *,
    status: TaskStatus,
    error_message: str | None = None,
    started: bool = False,
    finished: bool = False,
) -> None:
    task.status = status.value
    task.updated_at = utcnow()
    if started and task.started_at is None:
        task.started_at = utcnow()
    if finished:
        task.finished_at = utcnow()
    if error_message:
        task.error_message = error_message
    session.add(task)


def _load_params_json(task: Task) -> dict[str, Any]:
    if not task.params_json:
        return {}
    try:
        parsed = json.loads(task.params_json)
        if isinstance(parsed, dict):
            return parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return {}


def _build_target_tasks(task: Task) -> list[tuple[str | None, Task]]:
    params = _load_params_json(task)
    targets = params.get("generation_targets") if isinstance(params.get("generation_targets"), list) else []
    if not targets:
        return [(None, task)]

    derived: list[tuple[str | None, Task]] = []
    for raw_target in targets:
        if not isinstance(raw_target, dict):
            continue

        cloned = task.model_copy(deep=True)
        task_params = deepcopy(params)
        task_params["current_target"] = raw_target

        for key in ("aspect_ratio", "width", "height"):
            if raw_target.get(key) is not None:
                task_params[key] = raw_target.get(key)

        per_target_n = raw_target.get("n_outputs")
        if isinstance(per_target_n, int) and per_target_n > 0:
            cloned.n_outputs = per_target_n

        cloned.params_json = json.dumps(task_params, ensure_ascii=False)
        derived.append((str(raw_target.get("target_type") or "other"), cloned))

    return derived or [(None, task)]


@celery_app.task(name="generate_task")
def generate_task(task_id: str):
    try:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                logger.error("[task=%s][stage=load] task not found", task_id)
                return

            logger.info(
                "[task=%s][stage=start] type=%s provider=%s requested_outputs=%s image_model=%s optimizer_model=%s",
                task_id,
                task.type,
                task.provider,
                task.n_outputs,
                settings.google_image_model,
                settings.prompt_optimizer_model,
            )
            _update_task_status(session, task, status=TaskStatus.RUNNING, started=True)
            session.commit()
            session.refresh(task)

            provider = get_provider(task.provider)
            provider.validate_task_type(task)

            task_type = (task.type or "").strip().lower()
            targets = _build_target_tasks(task)
            logger.info(
                "[task=%s][stage=targets] count=%s params=%s",
                task_id,
                len(targets),
                _load_params_json(task),
            )
            all_outputs = []
            main_prompt = None

            for target_type, target_task in targets:
                logger.info(
                    "[task=%s][stage=provider_generate] provider=%s target=%s n_outputs=%s",
                    task_id,
                    provider.name,
                    target_type or "default",
                    target_task.n_outputs,
                )
                generated_outputs = provider.generate(target_task)
                if main_prompt is None:
                    main_prompt = target_task.prompt_final

                for item in generated_outputs:
                    all_outputs.append((target_type, item))

            task.prompt_final = main_prompt or task.prompt_final
            task.model_name = task.model_name or getattr(targets[0][1], "model_name", None)

            _update_task_status(session, task, status=TaskStatus.SAVING)

            if task_type in {TaskType.IMAGE.value, TaskType.VIDEO.value}:
                next_index = 1
                existing_count = session.exec(select(Output).where(Output.task_id == task_id)).all()
                if existing_count:
                    next_index = max(item.index for item in existing_count) + 1

                for target_type, item in all_outputs:
                    output = Output(
                        task_id=task_id,
                        index=next_index,
                        file_path=item.file_path,
                        mime_type=item.mime_type,
                        file_type=item.file_type,
                        file_name=item.file_name,
                        file_size=item.file_size,
                        width=item.width,
                        height=item.height,
                        duration_seconds=item.duration_seconds,
                        checksum=item.checksum,
                        target_type=target_type,
                    )
                    next_index += 1
                    session.add(output)
            elif task_type == TaskType.PROMPT.value:
                pass

            _update_task_status(session, task, status=TaskStatus.DONE, finished=True)
            session.commit()
            logger.info(
                "[task=%s][stage=done] provider=%s model=%s outputs=%s",
                task_id,
                task.provider,
                task.model_name,
                len(all_outputs),
            )
    except Exception as exc:  # noqa: BLE001
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if task:
                _update_task_status(
                    session,
                    task,
                    status=TaskStatus.FAILED,
                    error_message=(
                        f"[provider={task.provider or 'unknown'}][stage=generate]"
                        f"[{type(exc).__name__}] {exc!r}"
                    ),
                    finished=True,
                )
                session.commit()
        logger.exception("[task=%s][stage=failed] %s", task_id, exc)
        raise

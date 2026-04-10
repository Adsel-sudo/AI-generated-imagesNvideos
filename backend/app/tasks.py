import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from .celery_app import celery_app
from .config import settings
from .db import engine
from .enums import TaskStatus, TaskType
from .image_variants import ensure_image_variants
from .models import Output, Task, utcnow
from .providers.router import get_provider

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProviderTaskInput:
    id: str
    type: str | None
    provider: str | None
    request_text: str
    prompt_final: str | None
    params_json: str | None
    n_outputs: int
    model_name: str | None



def _update_task_status(
    session: Session,
    task: Task,
    *,
    status: TaskStatus,
    error_message: str | None = None,
    progress_message: str | None = None,
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
    if progress_message is not None:
        task.progress_message = progress_message
    session.add(task)



def _load_params_json(task: Task | ProviderTaskInput) -> dict[str, Any]:
    if not task.params_json:
        return {}
    try:
        parsed = json.loads(task.params_json)
        if isinstance(parsed, dict):
            return parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return {}



def _make_provider_task_input(task: Task, *, params_json: str | None = None, n_outputs: int | None = None) -> ProviderTaskInput:
    return ProviderTaskInput(
        id=str(task.id),
        type=task.type,
        provider=task.provider,
        request_text=task.request_text,
        prompt_final=task.prompt_final,
        params_json=params_json if params_json is not None else task.params_json,
        n_outputs=n_outputs if n_outputs is not None else task.n_outputs,
        model_name=task.model_name,
    )



def _build_target_tasks(task: Task) -> list[tuple[str | None, ProviderTaskInput]]:
    params = _load_params_json(task)
    targets = params.get("generation_targets") if isinstance(params.get("generation_targets"), list) else []
    if not targets:
        return [(None, _make_provider_task_input(task))]

    derived: list[tuple[str | None, ProviderTaskInput]] = []
    for raw_target in targets:
        if not isinstance(raw_target, dict):
            continue

        task_params = dict(params)
        task_params["current_target"] = raw_target

        for key in ("aspect_ratio", "width", "height"):
            if raw_target.get(key) is not None:
                task_params[key] = raw_target.get(key)

        per_target_n = raw_target.get("n_outputs")
        target_n_outputs = task.n_outputs
        if isinstance(per_target_n, int) and per_target_n > 0:
            target_n_outputs = per_target_n

        target_task = _make_provider_task_input(
            task,
            params_json=json.dumps(task_params, ensure_ascii=False),
            n_outputs=target_n_outputs,
        )
        derived.append((str(raw_target.get("target_type") or "other"), target_task))

    return derived or [(None, _make_provider_task_input(task))]


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
            task.progress_current = 0
            task.progress_total = task.n_outputs
            task.progress_message = f"生成中 0/{task.n_outputs}"
            session.commit()
            session.refresh(task)

            provider = get_provider(task.provider)
            provider.validate_task_type(task)

            task_type = (task.type or "").strip().lower()
            targets = _build_target_tasks(task)
            logger.info(
                "[task=%s][stage=targets] count=%s resolution=%s params=%s",
                task_id,
                len(targets),
                _load_params_json(task).get("resolution"),
                _load_params_json(task),
            )
            all_outputs = []
            main_prompt = None
            next_index = 1
            if task_type in {TaskType.IMAGE.value, TaskType.VIDEO.value}:
                existing_outputs = session.exec(select(Output).where(Output.task_id == task_id)).all()
                if existing_outputs:
                    next_index = max(item.index for item in existing_outputs) + 1

            def persist_output(target_type: str | None, item) -> None:
                nonlocal next_index
                if task_type not in {TaskType.IMAGE.value, TaskType.VIDEO.value}:
                    return
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
                task.progress_current = min(task.n_outputs, task.progress_current + 1)
                task.progress_total = task.n_outputs
                task.progress_message = f"生成中 {task.progress_current}/{task.progress_total}"
                task.updated_at = utcnow()
                session.add(task)
                session.commit()
                if (item.file_type or "").lower() == "image":
                    ensure_image_variants(Path(item.file_path))

            for target_type, target_task in targets:
                session.refresh(task)
                if task.status == TaskStatus.CANCELLED.value:
                    _update_task_status(
                        session,
                        task,
                        status=TaskStatus.CANCELLED,
                        progress_message=f"已停止 {task.progress_current}/{task.progress_total}",
                        finished=True,
                    )
                    session.commit()
                    logger.info(
                        "[task=%s][stage=cancelled_before_target] target=%s progress=%s/%s",
                        task_id,
                        target_type or "default",
                        task.progress_current,
                        task.progress_total,
                    )
                    return

                logger.info(
                    "[task=%s][stage=provider_generate] provider=%s target=%s n_outputs=%s resolution=%s",
                    task_id,
                    provider.name,
                    target_type or "default",
                    target_task.n_outputs,
                    _load_params_json(target_task).get("resolution"),
                )
                generated_outputs = provider.generate(
                    target_task,
                    on_output=lambda item, current_target=target_type: persist_output(current_target, item),
                )
                if main_prompt is None:
                    main_prompt = target_task.prompt_final

                for item in generated_outputs:
                    all_outputs.append((target_type, item))

            task.prompt_final = main_prompt or task.prompt_final
            task.model_name = task.model_name or getattr(targets[0][1], "model_name", None)

            if task_type == TaskType.PROMPT.value:
                pass

            session.refresh(task)
            if task.status == TaskStatus.CANCELLED.value:
                _update_task_status(
                    session,
                    task,
                    status=TaskStatus.CANCELLED,
                    progress_message=f"已停止 {task.progress_current}/{task.progress_total}",
                    finished=True,
                )
                session.commit()
                logger.info(
                    "[task=%s][stage=cancelled_after_generate] provider=%s model=%s outputs=%s",
                    task_id,
                    task.provider,
                    task.model_name,
                    len(all_outputs),
                )
                return

            task.progress_current = max(task.progress_current, len(all_outputs))
            task.progress_total = task.n_outputs
            _update_task_status(
                session,
                task,
                status=TaskStatus.DONE,
                progress_message=f"已完成 {task.progress_current}/{task.progress_total}",
                finished=True,
            )
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
                if task.status == TaskStatus.CANCELLED.value:
                    _update_task_status(
                        session,
                        task,
                        status=TaskStatus.CANCELLED,
                        progress_message=f"已停止 {task.progress_current}/{task.progress_total}",
                        finished=True,
                    )
                    session.commit()
                    logger.info("[task=%s][stage=cancelled_exception_ignored] %s", task_id, exc)
                    return
                _update_task_status(
                    session,
                    task,
                    status=TaskStatus.FAILED,
                    error_message=(
                        f"[provider={task.provider or 'unknown'}][stage=generate]"
                        f"[{type(exc).__name__}] {exc!r}"
                    ),
                    progress_message=f"失败 {task.progress_current}/{task.progress_total}",
                    finished=True,
                )
                session.commit()
        logger.exception("[task=%s][stage=failed] %s", task_id, exc)
        raise

from sqlmodel import Session

from .celery_app import celery_app
from .db import engine
from .enums import TaskStatus
from .models import Output, Task, utcnow
from .providers.router import get_provider


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


@celery_app.task(name="generate_task")
def generate_task(task_id: str):
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return

        _update_task_status(session, task, status=TaskStatus.RUNNING, started=True)
        session.commit()

    try:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return

            provider = get_provider(task.provider)
            provider.validate_task_type(task)
            generated_outputs = provider.generate(task)

            # Mark saving while output rows/files are being persisted/validated.
            _update_task_status(session, task, status=TaskStatus.SAVING)
            for item in generated_outputs:
                output = Output(
                    task_id=task_id,
                    index=item.index,
                    file_path=item.file_path,
                    mime_type=item.mime_type,
                    file_type=item.file_type,
                    file_name=item.file_name,
                    file_size=item.file_size,
                    width=item.width,
                    height=item.height,
                    duration_seconds=item.duration_seconds,
                    checksum=item.checksum,
                )
                session.add(output)

            _update_task_status(session, task, status=TaskStatus.DONE, finished=True)
            session.commit()
    except Exception as exc:  # noqa: BLE001
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if task:
                _update_task_status(
                    session,
                    task,
                    status=TaskStatus.FAILED,
                    error_message=f"[provider={task.provider or 'unknown'}][stage=generate] {exc}",
                    finished=True,
                )
                session.commit()
        raise

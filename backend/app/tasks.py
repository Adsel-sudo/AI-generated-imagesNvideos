import time
from sqlmodel import Session, select

from .celery_app import celery_app
from .db import engine
from .models import Output, Task, utcnow
from .providers.router import get_provider


@celery_app.task(name="mock_generate_task")
def mock_generate_task(task_id: str):
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            return
        task.status = "running"
        task.started_at = utcnow()
        session.add(task)
        session.commit()

    try:
        time.sleep(1)
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return
            provider = get_provider(task.provider)
            provider.validate_task_type(task)
            generated_outputs = provider.generate(task)

            for item in generated_outputs:
                output = Output(
                    task_id=task_id,
                    index=item.index,
                    file_path=item.file_path,
                    mime_type=item.mime_type,
                    file_type=item.file_type,
                    file_name=item.file_name,
                    file_size=item.file_size,
                )
                session.add(output)

            task.status = "done"
            task.finished_at = utcnow()
            session.add(task)
            session.commit()
    except Exception as exc:  # noqa: BLE001
        with Session(engine) as session:
            task = session.exec(select(Task).where(Task.id == task_id)).one_or_none()
            if task:
                task.status = "failed"
                task.error_message = str(exc)
                task.finished_at = utcnow()
                session.add(task)
                session.commit()
        raise

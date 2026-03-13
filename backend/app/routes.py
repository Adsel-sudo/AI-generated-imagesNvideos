from pathlib import Path
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, desc, select

from .config import settings
from .db import engine
from .models import Output, Task, utcnow
from .schemas import CreateTaskRequest
from .tasks import mock_generate_task

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/api/tasks")
def create_task(payload: CreateTaskRequest):
    with Session(engine) as session:
        task = Task(
            type=payload.type,
            provider=payload.provider,
            params_json=json.dumps(payload.params, ensure_ascii=False),
            request_text=payload.request_text,
            n_outputs=payload.n_outputs,
            status="pending",
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        celery_result = mock_generate_task.delay(task.id)
        task.status = "queued"
        task.celery_task_id = celery_result.id
        task.updated_at = utcnow()
        session.add(task)
        session.commit()
        session.refresh(task)

        return task


@router.get("/api/tasks")
def list_tasks():
    with Session(engine) as session:
        tasks = session.exec(select(Task).order_by(desc(Task.created_at))).all()
        return tasks


@router.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="task not found")

        outputs = session.exec(
            select(Output).where(Output.task_id == task_id).order_by(Output.index)
        ).all()

        return {
            **task.model_dump(),
            "outputs": [output.model_dump() for output in outputs],
        }


@router.get("/api/tasks/{task_id}/outputs/{output_id}")
def download_output(task_id: str, output_id: str):
    with Session(engine) as session:
        output = session.get(Output, output_id)
        if not output or output.task_id != task_id:
            raise HTTPException(status_code=404, detail="output not found")

    output_file = Path(output.file_path)
    if not output_file.exists():
        raise HTTPException(status_code=404, detail="file missing")

    return FileResponse(path=output_file, media_type=output.mime_type, filename=output_file.name)


@router.get("/api/tasks/{task_id}/download.zip")
def download_zip(task_id: str):
    task_output_dir = settings.data_dir / "outputs" / task_id
    if not task_output_dir.exists():
        raise HTTPException(status_code=404, detail="task output dir not found")

    zip_dir = settings.data_dir / "zips"
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / f"{task_id}.zip"

    if not zip_path.exists():
        import zipfile

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(task_output_dir.glob("*.png")):
                zf.write(file, arcname=file.name)

    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="zip not found")

    return FileResponse(path=zip_path, media_type="application/zip", filename=f"{task_id}.zip")

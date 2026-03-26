import json
import logging
import mimetypes
import zipfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, desc, select

from .constants import DEFAULT_PROVIDER
from .config import settings
from .db import engine
from .enums import TaskStatus
from .models import Output, Task, utcnow
from .prompt_optimizer import prompt_optimizer
from .schemas import (
    CreateTaskRequest,
    FileUploadResponse,
    PromptGenerateTaskRequest,
    PromptOptimizeRequest,
    PromptOptimizeResponse,
)
from .storage import get_task_zip_path
from .tasks import generate_task

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/api/files", response_model=FileUploadResponse)
def upload_file(file: UploadFile = File(...)):
    file_id = str(uuid4())
    suffix = Path(file.filename or "").suffix or ".bin"
    safe_name = Path(file.filename or f"{file_id}{suffix}").name
    final_name = f"{file_id}{suffix}"
    upload_dir = settings.uploads_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_path = upload_dir / final_name

    content = file.file.read()
    save_path.write_bytes(content)

    mime_type = file.content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    return FileUploadResponse(
        file_id=file_id,
        file_name=safe_name,
        file_path=str(save_path),
        mime_type=mime_type,
        file_size=save_path.stat().st_size,
        url=f"/api/files/{file_id}",
    )


@router.get("/api/files/{file_id}")
def get_uploaded_file(file_id: str):
    upload_dir = settings.uploads_dir
    matches = sorted(upload_dir.glob(f"{file_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="file not found")

    file_path = matches[0]
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return FileResponse(path=file_path, media_type=mime_type, filename=file_path.name)


@router.post("/api/prompt/optimize", response_model=PromptOptimizeResponse)
def optimize_prompt(payload: PromptOptimizeRequest):
    references = [item.model_dump() for item in payload.references]
    generation_targets = [item.model_dump() for item in payload.generation_targets]
    logger.info(
        "[stage=optimize_prompt] task_type=%s raw_len=%s refs=%s targets=%s optimizer_model=%s",
        payload.task_type,
        len((payload.raw_request or "").strip()),
        len(references),
        len(generation_targets),
        settings.prompt_optimizer_model,
    )
    try:
        optimized = prompt_optimizer.optimize(
            task_type=payload.task_type,
            raw_request=payload.raw_request,
            references=references,
            usage_options=payload.usage_options,
            generation_targets=generation_targets,
        )
        return PromptOptimizeResponse(**optimized)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "[stage=optimize_prompt][failed] task_type=%s refs=%s targets=%s err=%r",
            payload.task_type,
            len(references),
            len(generation_targets),
            exc,
        )
        raise


@router.post("/api/prompt/generate-task")
def generate_task_from_prompt(payload: PromptGenerateTaskRequest):
    params = dict(payload.params)
    params.update(
        {
            "optimized_prompt_cn": payload.optimized_prompt_cn,
            "structured_summary": payload.structured_summary,
            "references": [item.model_dump() for item in payload.references],
            "generation_targets": [item.model_dump() for item in payload.generation_targets],
            "usage_options": payload.usage_options,
            "confirm_notes": payload.confirm_notes,
        }
    )

    total_outputs = sum(item.n_outputs for item in payload.generation_targets) if payload.generation_targets else payload.n_outputs

    logger.info(
        "[stage=generate_task_from_prompt] provider=%s task_type=%s refs=%s targets=%s total_outputs=%s image_model=%s",
        payload.provider or DEFAULT_PROVIDER,
        payload.task_type,
        len(payload.references),
        len(payload.generation_targets),
        total_outputs,
        settings.google_image_model,
    )

    with Session(engine) as session:
        task = Task(
            type=payload.task_type,
            provider=payload.provider or DEFAULT_PROVIDER,
            params_json=json.dumps(params, ensure_ascii=False),
            request_text=payload.optimized_prompt_cn,
            prompt_final=payload.generation_prompt,
            n_outputs=total_outputs,
            progress_current=0,
            progress_total=total_outputs,
            progress_message="排队中",
            status=TaskStatus.QUEUED.value,
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        celery_result = generate_task.delay(task.id)
        task.celery_task_id = celery_result.id
        task.updated_at = utcnow()
        session.add(task)
        session.commit()
        session.refresh(task)

        return task


@router.post("/api/tasks")
def create_task(payload: CreateTaskRequest):
    with Session(engine) as session:
        task = Task(
            type=payload.type,
            provider=payload.provider or DEFAULT_PROVIDER,
            params_json=json.dumps(payload.params, ensure_ascii=False),
            request_text=payload.request_text,
            n_outputs=payload.n_outputs,
            progress_current=0,
            progress_total=payload.n_outputs,
            progress_message="排队中",
            status=TaskStatus.QUEUED.value,
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        celery_result = generate_task.delay(task.id)
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

        outputs = session.exec(select(Output).where(Output.task_id == task_id).order_by(Output.index)).all()

        outputs_data = [output.model_dump() for output in outputs]
        outputs_by_target: dict[str, list[dict]] = {}
        for item in outputs_data:
            group = item.get("target_type") or "default"
            outputs_by_target.setdefault(group, []).append(item)

        return {
            **task.model_dump(),
            "outputs": outputs_data,
            "outputs_by_target": outputs_by_target,
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
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="task not found")

        outputs = session.exec(select(Output).where(Output.task_id == task_id).order_by(Output.index)).all()

    valid_files = [Path(output.file_path) for output in outputs if output.file_path and Path(output.file_path).exists()]
    if not valid_files:
        raise HTTPException(status_code=404, detail="no output files found")

    zip_path = get_task_zip_path(task_id)
    if not zip_path.exists():
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in valid_files:
                zf.write(file, arcname=file.name)

    return FileResponse(path=zip_path, media_type="application/zip", filename=f"{task_id}.zip")

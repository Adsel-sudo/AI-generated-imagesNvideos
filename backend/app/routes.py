import json
import logging
import mimetypes
import zipfile
from datetime import UTC, datetime
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlmodel import Session, desc, select

from .constants import DEFAULT_PROVIDER
from .auth import require_login
from .config import settings
from .celery_app import celery_app
from .db import engine
from .enums import TaskStatus
from .image_variants import build_variant_path
from .models import Output, Task, utcnow
from .prompt_optimizer import prompt_optimizer
from .schemas import (
    CreateTaskRequest,
    FileUploadResponse,
    PromptGenerateTaskRequest,
    PromptOptimizeRequest,
    PromptOptimizeResponse,
    TaskDetailLiteResponse,
    TaskOutputsPageResponse,
)
from .storage import get_task_zip_path
from .tasks import generate_task

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_output_payload(task_id: str, output: Output) -> dict:
    original_path = Path(output.file_path)
    preview_path = build_variant_path(original_path, "preview")
    thumbnail_path = build_variant_path(original_path, "thumbnail")
    payload = output.model_dump()
    payload.update(
        {
            "original_path": str(original_path),
            "preview_path": str(preview_path) if preview_path.exists() else None,
            "thumbnail_path": str(thumbnail_path) if thumbnail_path.exists() else None,
            "original_url": f"/api/tasks/{task_id}/outputs/{output.id}",
            "preview_url": f"/api/tasks/{task_id}/outputs/{output.id}?variant=preview" if preview_path.exists() else None,
            "thumbnail_url": f"/api/tasks/{task_id}/outputs/{output.id}?variant=thumbnail"
            if thumbnail_path.exists()
            else None,
        }
    )
    return payload


def _build_cache_headers(output_file: Path) -> dict[str, str]:
    stat = output_file.stat()
    etag = f"\"{stat.st_mtime_ns:x}-{stat.st_size:x}\""
    last_modified = format_datetime(datetime.fromtimestamp(stat.st_mtime, tz=UTC), usegmt=True)
    return {
        "ETag": etag,
        "Last-Modified": last_modified,
        "Cache-Control": "private, max-age=31536000, immutable",
    }


def _is_not_modified(request: Request, output_file: Path, etag: str) -> bool:
    if_none_match = (request.headers.get("if-none-match") or "").strip()
    if if_none_match and if_none_match == etag:
        return True

    if_modified_since = request.headers.get("if-modified-since")
    if if_modified_since:
        try:
            since = parsedate_to_datetime(if_modified_since)
            file_mtime = output_file.stat().st_mtime
            if file_mtime <= since.timestamp():
                return True
        except Exception:  # noqa: BLE001
            return False
    return False


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/api/files", response_model=FileUploadResponse)
def upload_file(file: UploadFile = File(...), _=Depends(require_login)):
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
def get_uploaded_file(file_id: str, _=Depends(require_login)):
    upload_dir = settings.uploads_dir
    matches = sorted(upload_dir.glob(f"{file_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="file not found")

    file_path = matches[0]
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return FileResponse(path=file_path, media_type=mime_type, filename=file_path.name)


@router.post("/api/prompt/optimize", response_model=PromptOptimizeResponse)
def optimize_prompt(payload: PromptOptimizeRequest, _=Depends(require_login)):
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
def generate_task_from_prompt(payload: PromptGenerateTaskRequest, _=Depends(require_login)):
    params = dict(payload.params)
    usage_options = dict(payload.usage_options)
    usage_options["resolution"] = payload.resolution
    params.update(
        {
            "optimized_prompt_cn": payload.optimized_prompt_cn,
            "structured_summary": payload.structured_summary,
            "resolution": payload.resolution,
            "references": [item.model_dump() for item in payload.references],
            "generation_targets": [item.model_dump() for item in payload.generation_targets],
            "usage_options": usage_options,
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
def create_task(payload: CreateTaskRequest, _=Depends(require_login)):
    with Session(engine) as session:
        params = dict(payload.params)
        params["resolution"] = payload.resolution
        task = Task(
            type=payload.type,
            provider=payload.provider or DEFAULT_PROVIDER,
            params_json=json.dumps(params, ensure_ascii=False),
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
def list_tasks(_=Depends(require_login)):
    with Session(engine) as session:
        tasks = session.exec(select(Task).order_by(desc(Task.created_at))).all()
        return tasks


@router.get("/api/tasks/{task_id}", response_model=TaskDetailLiteResponse)
def get_task(task_id: str, _=Depends(require_login)):
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="task not found")

        total = session.exec(select(func.count()).select_from(Output).where(Output.task_id == task_id)).one()
        progress_total = max(0, int(task.progress_total or 0))
        progress_current = max(0, int(task.progress_current or 0))
        progress_percent = (progress_current / progress_total * 100) if progress_total > 0 else 0

        return TaskDetailLiteResponse(
            id=task.id,
            status=task.status,
            progress_current=progress_current,
            progress_total=progress_total,
            progress_percent=round(progress_percent, 2),
            message=task.progress_message,
            error=task.error_message,
            created_at=task.created_at,
            updated_at=task.updated_at,
            output_count=int(total or 0),
        )


@router.get("/api/tasks/{task_id}/outputs", response_model=TaskOutputsPageResponse)
def list_task_outputs(
    task_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _=Depends(require_login),
):
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="task not found")

        total = session.exec(select(func.count()).select_from(Output).where(Output.task_id == task_id)).one()
        start = (page - 1) * page_size
        items = session.exec(
            select(Output).where(Output.task_id == task_id).order_by(Output.index).offset(start).limit(page_size)
        ).all()

        return TaskOutputsPageResponse(
            task_id=task_id,
            page=page,
            page_size=page_size,
            total=int(total or 0),
            items=[_build_output_payload(task_id, item) for item in items],
        )


@router.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str, _=Depends(require_login)):
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="task not found")

        if task.status in {TaskStatus.DONE.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value}:
            return task

        task.status = TaskStatus.CANCELLED.value
        task.progress_message = "已停止"
        task.error_message = None
        task.updated_at = utcnow()
        task.finished_at = utcnow()
        session.add(task)
        session.commit()
        session.refresh(task)

        if task.celery_task_id:
            try:
                celery_app.control.revoke(task.celery_task_id, terminate=False)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[stage=cancel_task][task=%s] celery revoke failed: %s",
                    task_id,
                    exc,
                )

        return task


@router.get("/api/tasks/{task_id}/outputs/{output_id}")
def download_output(
    request: Request,
    task_id: str,
    output_id: str,
    variant: str = Query(default="original"),
    _=Depends(require_login),
):
    with Session(engine) as session:
        output = session.get(Output, output_id)
        if not output or output.task_id != task_id:
            raise HTTPException(status_code=404, detail="output not found")

    output_file = Path(output.file_path)
    normalized_variant = (variant or "original").strip().lower()
    if normalized_variant in {"preview", "thumbnail"}:
        candidate = build_variant_path(output_file, normalized_variant)
        if candidate.exists():
            output_file = candidate
        else:
            raise HTTPException(status_code=404, detail=f"{normalized_variant} file missing")
    if not output_file.exists():
        raise HTTPException(status_code=404, detail="file missing")

    cache_headers = _build_cache_headers(output_file)
    if _is_not_modified(request, output_file, cache_headers["ETag"]):
        return Response(status_code=304, headers=cache_headers)
    return FileResponse(path=output_file, media_type=output.mime_type, filename=output_file.name, headers=cache_headers)


@router.get("/api/tasks/{task_id}/download.zip")
def download_zip(task_id: str, _=Depends(require_login)):
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

"""Safer cleanup for persisted files and DB records."""

from __future__ import annotations

import argparse
import json
import stat
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, select

backend_dir = str(Path(__file__).resolve().parents[1])
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from app.config import settings
from app.image_variants import build_variant_path
from app.models import Output, Task

ACTIVE_STATUSES = {"queued", "running", "processing", "pending", "saving"}
FAILED_CANCELLED_STATUSES = {"failed", "cancelled"}
SUCCESS_STATUSES = {"done", "completed", "success", "succeeded"}


@dataclass(frozen=True)
class CleanupRule:
    key: str
    directory: Path
    retention_days: int


@dataclass
class CleanupStats:
    checked_files: int = 0
    skipped_active_task_files: int = 0
    deleted_files: int = 0
    reclaimed_bytes: int = 0
    db_tasks_deleted: int = 0
    db_outputs_deleted: int = 0
    db_orphan_outputs_deleted: int = 0
    db_skipped_active_tasks: int = 0
    db_skipped_unknown_status_tasks: int = 0
    db_skipped_due_file_errors: int = 0


def format_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{num_bytes} B"


def delete_file(path: Path, dry_run: bool) -> tuple[bool, int]:
    if not path.exists() or not path.is_file():
        return True, 0
    size = path.stat().st_size
    if dry_run:
        return True, size
    path.unlink()
    return True, size


def is_active_output_file(path: Path, outputs_root: Path, active_task_ids: set[str]) -> bool:
    try:
        rel = path.relative_to(outputs_root)
    except ValueError:
        return False
    if not rel.parts:
        return False
    return rel.parts[0] in active_task_ids


def is_protected_upload_file(path: Path, protected_upload_paths: set[Path]) -> bool:
    return path.resolve() in protected_upload_paths


def _extract_reference_paths(task: Task) -> set[Path]:
    if not task.params_json:
        return set()
    try:
        params = json.loads(task.params_json)
    except json.JSONDecodeError:
        return set()
    references = params.get("references") if isinstance(params, dict) else None
    if not isinstance(references, list):
        return set()

    result: set[Path] = set()
    for item in references:
        if not isinstance(item, dict):
            continue
        raw_path = item.get("file_path")
        if isinstance(raw_path, str) and raw_path.strip():
            result.add(Path(raw_path).resolve())
    return result


def collect_active_task_context() -> tuple[set[str], set[Path]]:
    active_task_ids: set[str] = set()
    protected_upload_paths: set[Path] = set()
    with Session(settings_sql_engine()) as session:
        active_tasks = session.exec(
            select(Task).where(Task.status.in_(tuple(ACTIVE_STATUSES)))
        ).all()
        for task in active_tasks:
            active_task_ids.add(task.id)
            protected_upload_paths.update(_extract_reference_paths(task))
    return active_task_ids, protected_upload_paths


def cleanup_directory(
    *,
    rule: CleanupRule,
    now_ts: float,
    dry_run: bool,
    active_task_ids: set[str],
    protected_upload_paths: set[Path],
    stats: CleanupStats,
) -> None:
    path = rule.directory
    if not path.exists() or not path.is_dir():
        print(f"[SKIP] {rule.key}: {path} does not exist.")
        return

    expire_before = now_ts - rule.retention_days * 24 * 60 * 60
    local_deleted = 0
    local_reclaimed = 0

    for item in path.rglob("*"):
        if not item.exists():
            continue
        try:
            item_stat = item.stat(follow_symlinks=False)
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if not stat.S_ISREG(item_stat.st_mode):
            continue
        stats.checked_files += 1
        if item_stat.st_mtime > expire_before:
            continue
        if rule.key == "outputs" and is_active_output_file(item, path, active_task_ids):
            stats.skipped_active_task_files += 1
            continue
        if rule.key == "uploads" and is_protected_upload_file(item, protected_upload_paths):
            stats.skipped_active_task_files += 1
            continue
        try:
            ok, reclaimed = delete_file(item, dry_run=dry_run)
            if ok:
                local_deleted += 1
                local_reclaimed += reclaimed
        except (FileNotFoundError, PermissionError, OSError) as exc:
            print(f"[WARN] {rule.key}: failed to delete {item}: {exc}")
            continue

    stats.deleted_files += local_deleted
    stats.reclaimed_bytes += local_reclaimed
    action = "would delete" if dry_run else "deleted"
    print(
        f"[DONE] {rule.key}: {action} {local_deleted} files, "
        f"reclaim {format_bytes(local_reclaimed)} from {path}"
    )


def _task_expire_before(task: Task) -> datetime | None:
    status = (task.status or "").strip().lower()
    if status in ACTIVE_STATUSES:
        return None
    if status in FAILED_CANCELLED_STATUSES:
        days = settings.cleanup_failed_cancelled_retention_days
    elif status in SUCCESS_STATUSES:
        days = settings.cleanup_success_retention_days
    else:
        return None
    base = task.finished_at or task.updated_at or task.created_at
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base + timedelta(days=days)


def cleanup_database(*, dry_run: bool, stats: CleanupStats) -> None:
    now = datetime.now(timezone.utc)
    with Session(settings_sql_engine()) as session:
        # 1) orphan output records (task missing)
        orphan_outputs = session.exec(
            select(Output).where(Output.task_id.not_in(select(Task.id)))
        ).all()
        for output in orphan_outputs:
            if dry_run:
                stats.db_orphan_outputs_deleted += 1
                continue
            session.delete(output)
            stats.db_orphan_outputs_deleted += 1
        if not dry_run and orphan_outputs:
            session.commit()

        # 2) expired task + outputs cleanup
        cleanup_candidate_statuses = tuple(FAILED_CANCELLED_STATUSES | SUCCESS_STATUSES)
        candidate_tasks = session.exec(
            select(Task).where(Task.status.in_(cleanup_candidate_statuses))
        ).all()
        for task in candidate_tasks:
            status = (task.status or "").strip().lower()
            if status in ACTIVE_STATUSES:
                stats.db_skipped_active_tasks += 1
                continue
            expire_at = _task_expire_before(task)
            if expire_at is None:
                stats.db_skipped_unknown_status_tasks += 1
                continue
            if now < expire_at:
                continue

            related_outputs = session.exec(
                select(Output).where(Output.task_id == task.id)
            ).all()
            file_delete_error = False
            file_candidates: list[Path] = []
            for output in related_outputs:
                original = Path(output.file_path)
                file_candidates.extend(
                    [
                        original,
                        build_variant_path(original, "preview"),
                        build_variant_path(original, "thumbnail"),
                    ]
                )
            file_candidates.append(settings.zips_dir / f"{task.id}.zip")
            unique_candidates = {candidate for candidate in file_candidates}

            for candidate in unique_candidates:
                try:
                    delete_file(candidate, dry_run=dry_run)
                except (PermissionError, OSError) as exc:
                    print(f"[WARN] task={task.id} file delete failed: {candidate} err={exc}")
                    file_delete_error = True
                    break

            if file_delete_error:
                stats.db_skipped_due_file_errors += 1
                continue

            if dry_run:
                stats.db_outputs_deleted += len(related_outputs)
                stats.db_tasks_deleted += 1
                continue

            for output in related_outputs:
                session.delete(output)
            session.delete(task)
            session.commit()
            stats.db_outputs_deleted += len(related_outputs)
            stats.db_tasks_deleted += 1


def settings_sql_engine():
    from app.db import engine

    return engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cleanup expired files and stale DB records safely.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions only; do not delete files/records.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dry_run = bool(args.dry_run)

    rules = [
        CleanupRule("uploads", settings.uploads_dir, settings.cleanup_uploads_retention_days),
        CleanupRule("outputs", settings.outputs_dir, settings.cleanup_outputs_retention_days),
        CleanupRule("zips", settings.zips_dir, settings.cleanup_zips_retention_days),
        CleanupRule("logs", settings.logs_dir, settings.cleanup_logs_retention_days),
    ]

    now_ts = time.time()
    stats = CleanupStats()

    print(f"[START] safer cleanup dry_run={dry_run}")
    active_task_ids, protected_upload_paths = collect_active_task_context()
    print(
        f"[INFO] active task ids protected={len(active_task_ids)} "
        f"protected_upload_refs={len(protected_upload_paths)}"
    )

    for rule in rules:
        cleanup_directory(
            rule=rule,
            now_ts=now_ts,
            dry_run=dry_run,
            active_task_ids=active_task_ids,
            protected_upload_paths=protected_upload_paths,
            stats=stats,
        )

    cleanup_database(dry_run=dry_run, stats=stats)

    mode = "DRY-RUN SUMMARY" if dry_run else "SUMMARY"
    print(
        f"[{mode}] files_checked={stats.checked_files} files_deleted={stats.deleted_files} "
        f"reclaimed={format_bytes(stats.reclaimed_bytes)} active_file_protected={stats.skipped_active_task_files} "
        f"db_tasks_deleted={stats.db_tasks_deleted} db_outputs_deleted={stats.db_outputs_deleted} "
        f"db_orphan_outputs_deleted={stats.db_orphan_outputs_deleted} db_active_tasks_skipped={stats.db_skipped_active_tasks} "
        f"db_unknown_status_skipped={stats.db_skipped_unknown_status_tasks} db_file_error_skipped={stats.db_skipped_due_file_errors}"
    )


if __name__ == "__main__":
    main()

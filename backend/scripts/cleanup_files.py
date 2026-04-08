"""Periodic cleanup for persisted files under data/ directories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat
import time


@dataclass(frozen=True)
class CleanupRule:
    directory: Path
    retention_days: int


def format_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{num_bytes} B"


def cleanup_directory(path: Path, retention_days: int, now_ts: float) -> tuple[int, int]:
    if not path.exists() or not path.is_dir():
        print(f"[SKIP] {path} does not exist.")
        return 0, 0

    expire_before = now_ts - retention_days * 24 * 60 * 60
    deleted_count = 0
    reclaimed_bytes = 0

    for item in path.rglob("*"):
        if not item.exists():
            continue

        try:
            item_stat = item.stat(follow_symlinks=False)
        except (FileNotFoundError, PermissionError, OSError):
            continue

        if not stat.S_ISREG(item_stat.st_mode):
            continue

        if item_stat.st_mtime > expire_before:
            continue

        file_size = item_stat.st_size
        try:
            item.unlink()
        except (FileNotFoundError, PermissionError, OSError):
            continue

        deleted_count += 1
        reclaimed_bytes += file_size

    print(
        f"[DONE] {path}: deleted {deleted_count} files, reclaimed {format_bytes(reclaimed_bytes)}"
    )
    return deleted_count, reclaimed_bytes


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    data_root = repo_root / "data"

    rules = [
        CleanupRule(data_root / "uploads", 45),
        CleanupRule(data_root / "outputs", 120),
        CleanupRule(data_root / "zips", 7),
        CleanupRule(data_root / "logs", 30),
    ]

    now_ts = time.time()
    total_deleted = 0
    total_reclaimed = 0

    print("[START] Cleanup expired files")
    for rule in rules:
        deleted_count, reclaimed_bytes = cleanup_directory(
            rule.directory, rule.retention_days, now_ts
        )
        total_deleted += deleted_count
        total_reclaimed += reclaimed_bytes

    print(
        f"[SUMMARY] deleted {total_deleted} files in total, "
        f"reclaimed {format_bytes(total_reclaimed)}"
    )


if __name__ == "__main__":
    main()

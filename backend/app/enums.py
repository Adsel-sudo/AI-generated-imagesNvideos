from enum import Enum


class StrEnum(str, Enum):
    pass


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SAVING = "saving"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    PROMPT = "prompt"

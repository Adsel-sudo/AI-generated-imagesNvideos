from .enums import TaskStatus

DEFAULT_PROVIDER = "mock"

STATUS_FINAL = {TaskStatus.DONE.value, TaskStatus.FAILED.value}

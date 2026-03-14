from .enums import TaskStatus

DEFAULT_PROVIDER = "mock"
DEFAULT_TASK_TYPE = "image"
DEFAULT_N_OUTPUTS = 1

STATUS_FINAL = {TaskStatus.DONE.value, TaskStatus.FAILED.value}

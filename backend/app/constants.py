from .enums import TaskStatus

DEFAULT_PROVIDER = "google_image"
DEFAULT_TASK_TYPE = "image"
DEFAULT_N_OUTPUTS = 3

STATUS_FINAL = {TaskStatus.DONE.value, TaskStatus.FAILED.value}

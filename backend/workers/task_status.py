"""No asynchronous task states exist in the current request-response MVP."""


def get_task_status(_task_id: str):
    raise NotImplementedError("Background task status is not implemented.")

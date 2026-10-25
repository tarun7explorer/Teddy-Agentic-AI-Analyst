"""Retry policy is deferred until background jobs are introduced."""


def retry_task(_task):
    raise NotImplementedError("Background task retries are not implemented.")

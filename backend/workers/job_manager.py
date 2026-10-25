"""Background jobs are deferred; current processing is synchronous and bounded."""


def enqueue(_job):
    raise NotImplementedError("No background job backend is configured.")

"""Deferred database integration; no database dependency is configured."""


def get_database():
    raise NotImplementedError("Persistent database storage is not implemented.")

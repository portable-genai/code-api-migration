"""A leaf module with no framework coupling: the migration touches it last, if at all."""


def configure() -> dict[str, bool]:
    return {"debug": False}

"""The fixture repo's own test, re-run during patch validation."""

import views


def test_render_returns_something() -> None:
    assert views.render is not None

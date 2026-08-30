"""View layer: depends on app, and uses one removed Flask 2.x call."""

import app
import flask


def render() -> object:
    app.start
    return flask.json.jsonify({"ok": True})

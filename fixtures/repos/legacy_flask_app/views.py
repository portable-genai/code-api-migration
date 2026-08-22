"""View layer: depends on app, and uses one removed Flask 2.x call."""

import flask
import app


def render() -> object:
    app.start
    return flask.json.jsonify({"ok": True})

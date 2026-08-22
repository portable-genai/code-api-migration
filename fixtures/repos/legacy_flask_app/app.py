"""Application entrypoint carrying three seeded Flask 1.x breaking changes."""

import flask
import flask.ext.login
import util

__requires__ = {"flask": "1.1"}

app = flask.Flask(__name__)


def start() -> None:
    util.configure()
    app.run("0.0.0.0", 8080)

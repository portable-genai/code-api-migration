"""Half of an import cycle, also carrying two seeded requests breaking changes."""

import beta
import requests

__requires__ = {"requests": "2.10"}


def a() -> object:
    return requests.session()


def call_b() -> object:
    return beta.b()

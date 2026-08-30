"""The other half of the import cycle."""

import alpha


def b() -> object:
    return alpha.a()

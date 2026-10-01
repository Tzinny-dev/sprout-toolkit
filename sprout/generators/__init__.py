"""Registry of generation plug-ins.

Every generator is a subclass of ``Generator`` with a unique ``id``. The
spec references generators by their ``id`` (the item's ``generator`` field).

Built-ins are registered here; third-party generators advertised under the
``sprout.generators`` entry-point group are merged on top by ``plugins.py``.
Built-in ids always win, so installing a plug-in cannot change the output
of an existing spec.

Principles: strict determinism (seed -> bytes), zero network access, and
a separation between "base shapes" (masks) and "fill" (noise).
"""
from __future__ import annotations

from .base import FrameData, Generator
from .blob_walk import BlobWalk
from .critter import Critter
from .face import Face
from .flora import Flora
from .font import Font
from .particles import Particles
from .props import Props
from .terrain import Terrain
from .ui import Ui

BUILTIN_GENERATORS: dict[str, type[Generator]] = {
    Terrain.id: Terrain,
    Props.id: Props,
    Particles.id: Particles,
    BlobWalk.id: BlobWalk,
    Critter.id: Critter,
    Flora.id: Flora,
    Face.id: Face,
    Ui.id: Ui,
    Font.id: Font,
}

GENERATORS: dict[str, type[Generator]] = dict(BUILTIN_GENERATORS)


def _load_plugins() -> None:
    """Merge entry-point generators into ``GENERATORS`` (never raises)."""
    from .. import plugins  # local: plugins imports this module

    try:
        plugins.load_into(GENERATORS)
    except Exception:  # noqa: BLE001 - discovery must never break the CLI
        pass


_load_plugins()


def get_generator(identifier: str) -> type[Generator]:
    if identifier not in GENERATORS:
        raise KeyError(f"unknown generator: {identifier}")
    return GENERATORS[identifier]


def plugin_generator_ids() -> list[str]:
    """Ids contributed by plug-ins (i.e. not built in)."""
    return sorted(set(GENERATORS) - set(BUILTIN_GENERATORS))


__all__ = [
    "FrameData",
    "Generator",
    "GENERATORS",
    "BUILTIN_GENERATORS",
    "get_generator",
    "plugin_generator_ids",
]

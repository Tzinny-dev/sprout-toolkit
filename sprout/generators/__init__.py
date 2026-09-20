"""Registry of generation plug-ins.

Every generator is a subclass of ``Generator`` with a unique ``id``. The
spec references generators by their ``id`` (the item's ``generator`` field).

Principles: strict determinism (seed -> bytes), zero network access, and a
separation between "base shapes" (masks) and "fill" (noise).
"""
from __future__ import annotations

from .base import FrameData, Generator
from .blob_walk import BlobWalk
from .font import Font
from .particles import Particles
from .props import Props
from .terrain import Terrain
from .ui import Ui

GENERATORS: dict[str, type[Generator]] = {
    Terrain.id: Terrain,
    Props.id: Props,
    Particles.id: Particles,
    BlobWalk.id: BlobWalk,
    Ui.id: Ui,
    Font.id: Font,
}


def get_generator(identifier: str) -> type[Generator]:
    if identifier not in GENERATORS:
        raise KeyError(f"unknown generator: {identifier}")
    return GENERATORS[identifier]


__all__ = ["FrameData", "Generator", "GENERATORS", "get_generator"]
"""Registro de plug-ins de generación.

Todo generador es una subclase de ``Generator`` con ``id`` único. La spec
referencia generadores por su ``id`` (campo ``generator`` del item).

Principios: determinismo estricto (seed -> bytes), cero red, y separación
entre "base shapes" (máscaras) y "relleno" (noise).
"""
from __future__ import annotations

from .base import FrameData, Generator
from .blob_walk import BlobWalk
from .particles import Particles
from .props import Props
from .terrain import Terrain

GENERATORS: dict[str, type[Generator]] = {
    Terrain.id: Terrain,
    Props.id: Props,
    Particles.id: Particles,
    BlobWalk.id: BlobWalk,
}


def get_generator(identifier: str) -> type[Generator]:
    if identifier not in GENERATORS:
        raise KeyError(f"generator desconocido: {identifier}")
    return GENERATORS[identifier]


__all__ = ["FrameData", "Generator", "GENERATORS", "get_generator"]
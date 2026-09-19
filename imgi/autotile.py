"""Autotiling 16 / 47 — reducción canónica de máscaras de vecindad 8-bit.

Bits (convención canónica imgi, ver INVESTIGACION.md §5.3)::

    N=1, NE=2, E=4, SE=8, S=16, SW=32, W=64, NW=128

El bit diagonal solo cuenta si **ambos** cardinales adyacentes están presentes:
así 2**8 = 256 vecindades colapsan a 47. Un "corner bit" describe el cuadrante
donde se juntan sus dos lados; si falta un lado, ese cuadrante ya es borde
exterior y la diagonal no aporta una silueta distinta.

Referencia verificada contra Godot 4.7 (Blobsmith Autotile Wirer, MIT):
https://github.com/leobaray/blobsmith-autotile-wirer/blob/master/docs/why-47-tiles-not-256.md
"""
from __future__ import annotations

N, NE, E, SE, S, SW, W, NW = 1, 2, 4, 8, 16, 32, 64, 128

SIDES = N | E | S | W  # 0b01010101 == 85
CORNERS = NE | SE | SW | NW

BITMASK = "N1,E4,S16,W64,NE2,SE8,SW32,NW128"


def canonical_47(mask: int) -> int:
    """Máscara canónica del sistema 8-bit (47 clases)."""
    m = mask & SIDES
    if (mask & NE) and (mask & N) and (mask & E):
        m |= NE
    if (mask & SE) and (mask & S) and (mask & E):
        m |= SE
    if (mask & SW) and (mask & S) and (mask & W):
        m |= SW
    if (mask & NW) and (mask & N) and (mask & W):
        m |= NW
    return m


def canonical_16(mask: int) -> int:
    """Máscara canónica del sistema cardinal (16 clases, Match Sides)."""
    return mask & SIDES


def canonical(mask: int, size: int) -> int:
    if size == 16:
        return canonical_16(mask)
    if size == 47:
        return canonical_47(mask)
    raise ValueError(f"autotile no soportado: {size!r} (esperado 16 | 47)")


def masks(size: int) -> list[int]:
    """Máscaras canónicas en orden ascendente = orden de la hoja (cols=8)."""
    fn = {16: canonical_16, 47: canonical_47}.get(size)
    if fn is None:
        raise ValueError(f"autotile no soportado: {size!r} (esperado 16 | 47)")
    return [m for m in range(256) if fn(m) == m]

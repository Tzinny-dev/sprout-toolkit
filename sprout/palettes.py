"""Named color palettes + outline rules.

Generic art data: a palette is a named set of color roles (`fill`,
`accent`, `outline`) that any item can pull via ``params.palette``.
Explicit ``params.fill``/``outline`` always win over the palette, so a
palette only fills what the spec left out.

The outline rule keeps sprites consistent across generators:
``outline = darken(fill, 0.55)`` and ``width = max(1, frame_px // 32)``.
"""
from __future__ import annotations

RGB = tuple[int, int, int]

OUTLINE_DARKEN = 0.55


def darken(color: RGB, k: float = OUTLINE_DARKEN) -> RGB:
    """Scale an RGB triple toward black, clamped to 0..255."""
    return tuple(max(0, min(255, int(round(c * k)))) for c in color)  # type: ignore[return-value]


def outline_color(fill: RGB, k: float = OUTLINE_DARKEN) -> RGB:
    """Derived outline for a fill color (the single outline rule)."""
    return darken(fill, k)


def outline_width(frame_px: int) -> int:
    """Outline width in pixels that scales with the frame size."""
    return max(1, frame_px // 32)


def _palette(fill: RGB, accent: RGB) -> dict[str, list[int]]:
    return {
        "fill": list(fill),
        "accent": list(accent),
        "outline": list(outline_color(fill)),
    }


PALETTES: dict[str, dict[str, list[int]]] = {
    "earth": _palette((176, 124, 74), (232, 194, 106)),
    "forest": _palette((94, 152, 78), (168, 208, 96)),
    "ocean": _palette((72, 132, 196), (128, 208, 224)),
    "candy": _palette((232, 120, 160), (255, 214, 226)),
}


def get_palette(name: str) -> dict[str, list[int]]:
    return PALETTES[name]


def resolve_params(params: dict) -> None:
    """Fill in unset color roles from ``params['palette']`` (in place).

    Unknown palette names raise ``KeyError``; the spec loader turns that
    into a ``SpecError``. Existing keys are never overwritten.
    """
    name = params.get("palette")
    if name is None:
        return
    palette = get_palette(str(name))
    for role, value in palette.items():
        params.setdefault(role, list(value))

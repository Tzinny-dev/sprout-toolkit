"""Form-coverage measurement: which items share the same form params.

Identity comes from the spec, not from the pixels. ``render_items`` hands
every generator a running ``base`` offset, so one item renders different
detail depending on where it sits in the spec — and that detail noise
(96 bits *within* a form) swamps the form signal (192 bits *between*
forms) in generators like ``props``, where shape lives in the alpha
channel while seed varies the texture. Params are the only stable,
position-independent statement of what an item *is*.

Cosmetic params are dropped before grouping: palette names and anything
that is a colour describe the same form painted differently, so two
items differing only in tint are one form, not two.

A collision is two items agreeing on generator, frame count, autotile and
every structural param — the effective vocabulary is smaller than the
catalog claims. With a catalog of many species sampled from a handful of
forms, the species that share a form collect here, which is the gap
worth fixing. ``frames`` is part of the identity because a 4-frame blink
of ``happy`` is not the 1-frame still of it, even though both carry
``mood: happy``.

Measured on the built-in specs (13): every item is authored with its own
identity, so all 13 report zero collisions.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .spec import Item

COSMETIC_KEYS = frozenset({
    "palette", "colors", "color", "tint", "bg", "fg",
    "background", "foreground", "outline", "ink",
})


def is_color(value: Any) -> bool:
    """True for a colour literal: ``#rrggbb`` or an ``[r, g, b]`` triple."""
    if isinstance(value, str):
        return value.startswith("#")
    if isinstance(value, (list, tuple)) and len(value) in (3, 4):
        return all(isinstance(n, (int, float)) and not isinstance(n, bool)
                   for n in value)
    return False


def _freeze(value: Any) -> Any:
    """Make a param value hashable so signatures can be compared."""
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
    return value


def form_signature(item: "Item") -> tuple:
    """Canonical identity of an item: how it is generated, not where it sits.

    ``frames`` and ``autotile`` belong to it because they change what is
    delivered — a 4-frame blink of ``happy`` is not the same item as the
    1-frame still. ``tint`` is dropped with the colours: it only says
    whether runtime recolouring is allowed, which is the same form
    painted differently.
    """
    structural = (
        (key, _freeze(value))
        for key, value in item.params.items()
        if key not in COSMETIC_KEYS and not is_color(value)
    )
    return (item.generator, item.frames, item.autotile,
            tuple(sorted(structural)))


def diversity_groups(items: list["Item"]) -> list[list[str]]:
    """Item ids grouped by form (only groups with more than one member).

    Order follows the spec; members follow the order they appear in it.
    """
    seen: dict[tuple, list[str]] = {}
    for item in items:
        seen.setdefault(form_signature(item), []).append(item.id)
    return [members for members in seen.values() if len(members) > 1]


def distinct_forms(items: list["Item"]) -> int:
    """How many different forms the catalog actually contains."""
    return len({form_signature(item) for item in items})

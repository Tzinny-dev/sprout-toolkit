"""Form-coverage measurement: which items render to the same sprite.

The metric is deliberately perceptual rather than exact. Two items whose
alpha silhouettes differ by fewer than ``FORM_TOLERANCE`` cells on a
``FORM_GRID`` x ``FORM_GRID`` thumbnail are the same *form* — they may
differ in tint or in a few pixels of anatomy, but a player reads them as
the same thing. That is the coverage gap worth reporting.

Exact byte comparison would miss it: anatomy derives from the seed slot,
so two species sharing a form never produce identical pixels.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from .exporter import FrameData
    from .spec import Item

FORM_GRID = 16
FORM_TOLERANCE = 12  # of 256 cells


def form_signature(image: "Image.Image") -> bytes:
    """Alpha silhouette downsampled to a FORM_GRID x FORM_GRID thumbnail."""
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    return image.getchannel("A").resize(
        (FORM_GRID, FORM_GRID), Image.LANCZOS).tobytes()


def hamming(a: bytes, b: bytes) -> int:
    """Number of differing bits between two equal-length signatures."""
    return sum(bin(x ^ y).count("1") for x, y in zip(a, b))


def diversity_groups(
    items: list["Item"],
    items_frames: list[list["FrameData"]],
) -> list[list[str]]:
    """Item ids grouped by rendered form (groups with >1 member).

    Compares each item's first frame against the representative of every
    existing group; the first match wins, otherwise a new group is opened.
    O(n^2) in the worst case, which is fine for catalog-sized specs.
    """
    groups: list[tuple[bytes, list[str]]] = []
    for item, frames in zip(items, items_frames):
        if not frames:
            continue
        sig = form_signature(frames[0].image)
        for rep, members in groups:
            if hamming(sig, rep) <= FORM_TOLERANCE:
                members.append(item.id)
                break
        else:
            groups.append((sig, [item.id]))
    return [members for _, members in groups if len(members) > 1]


def distinct_forms(items_frames: list[list["FrameData"]]) -> int:
    """How many items have at least one frame (the renderable population)."""
    return sum(1 for frames in items_frames if frames)

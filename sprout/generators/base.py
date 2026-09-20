"""Contract for generation plug-ins."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image


@dataclass
class FrameData:
    id: str
    image: "Image.Image"  # RGBA, frame_px x frame_px
    meta: dict = field(default_factory=dict)


class Generator:
    """Base class. Generators produce deterministic frames given a seed."""

    id = ""

    def generate(
        self,
        seed: int,
        count: int,
        frame_px: int,
        params: dict,
        base: int = 0,  # global index of the first frame (for position-based variation)
    ) -> list[FrameData]:
        raise NotImplementedError
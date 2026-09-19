"""Contrato de los plug-ins de generación."""
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
    """Clase base. Los generadores producen frames deterministas dado un seed."""

    id = ""

    def generate(
        self,
        seed: int,
        count: int,
        frame_px: int,
        params: dict,
        base: int = 0,  # índice global del primer frame (para variación por posición)
    ) -> list[FrameData]:
        raise NotImplementedError
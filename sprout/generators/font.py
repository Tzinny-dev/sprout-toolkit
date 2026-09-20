"""Generador ``font``: bitmap font desde un TTF/OTF real (vía PIL/FreeType),
un glifo por frame.

A diferencia del resto de generadores (100% procedurales), ``font`` depende
de un archivo de fuente en disco. Por defecto usa la fuente empaquetada en
``sprout/assets/fonts/DejaVuSansMono-Bold.ttf`` (licencia Bitstream Vera, ver
``.LICENSE.txt`` junto al archivo) — vive **dentro** del paquete `sprout`
(no en `cli/assets/`) para que un `pip install` real (no editable) la
incluya vía `[tool.setuptools.package-data]`; ``font_path`` permite apuntar
a otra fuente.

Parámetros de spec (item.params):
    chars     : caracteres a generar, uno por frame (default ASCII imprimible
                32-126, 95 caracteres). ``frames`` debe ser igual a
                ``len(chars)``.
    font_path : ruta a un .ttf/.otf (default: fuente empaquetada).
    size      : tamaño de fuente en puntos/px (default 0.6 * frame_px).
    fill      : [r, g, b]  color del glifo (default blanco — pensado para
                tintarse en runtime).

El render no depende del ``seed``: es una rasterización determinista de la
fuente, igual que ``panel`` en ``ui.py``. El espacio (0x20) es un frame
legítimamente vacío (sin tinta) — no es un bug.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .base import FrameData, Generator

DEFAULT_CHARS = "".join(chr(c) for c in range(32, 127))  # ASCII imprimible

BUNDLED_FONT = (
    Path(__file__).resolve().parents[1] / "assets" / "fonts" / "DejaVuSansMono-Bold.ttf"
)


def resolve_font_path(params: dict) -> str:
    return str(params.get("font_path") or BUNDLED_FONT)


class Font(Generator):
    """Atlas de glifos: un frame por carácter, con métricas de avance."""

    id = "font"

    def generate(
        self,
        seed: int,
        count: int,
        frame_px: int,
        params: dict,
        base: int = 0,
    ) -> list[FrameData]:
        chars = params.get("chars", DEFAULT_CHARS)
        if count != len(chars):
            raise ValueError(
                f"font: frames debe ser {len(chars)} (uno por carácter en "
                f"'chars'), recibido {count}"
            )

        font_path = resolve_font_path(params)
        size = int(params.get("size", frame_px * 0.6))
        fill = tuple(int(c) for c in params.get("fill", [255, 255, 255]))
        try:
            face = ImageFont.truetype(font_path, size)
        except OSError as e:
            raise ValueError(f"font.font_path no se pudo cargar: {font_path} ({e})") from e

        pad = max(2, int(frame_px * 0.06))
        out: list[FrameData] = []
        for ch in chars:
            img = Image.new("RGBA", (frame_px, frame_px), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((pad, pad), ch, font=face, fill=fill + (255,))
            advance = round(face.getlength(ch))
            out.append(FrameData(id="", image=img, meta={"char": ch, "advance": advance}))
        return out

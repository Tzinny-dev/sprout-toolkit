"""``font`` generator: bitmap font from a real TTF/OTF (via PIL/FreeType),
one glyph per frame.

Unlike the rest of the generators (100% procedural), ``font`` depends on a
font file on disk. By default it uses the font bundled at
``sprout/assets/fonts/DejaVuSansMono-Bold.ttf`` (Bitstream Vera license, see
``.LICENSE.txt`` next to the file) — it lives **inside** the `sprout`
package (not in `cli/assets/`) so that a real `pip install` (non-editable)
includes it via `[tool.setuptools.package-data]`; ``font_path`` lets you
point to a different font.

Spec parameters (item.params):
    chars     : characters to generate, one per frame (default: printable
                ASCII 32-126, 95 characters). ``frames`` must equal
                ``len(chars)``.
    font_path : path to a .ttf/.otf (default: bundled font).
    size      : font size in points/px (default 0.6 * frame_px).
    fill      : [r, g, b]  glyph color (default white — meant to be
                tinted at runtime).

Rendering does not depend on ``seed``: it's a deterministic rasterization of
the font, just like ``panel`` in ``ui.py``. The space character (0x20) is a
legitimately empty frame (no ink) — not a bug.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .base import FrameData, Generator

DEFAULT_CHARS = "".join(chr(c) for c in range(32, 127))  # printable ASCII

BUNDLED_FONT = (
    Path(__file__).resolve().parents[1] / "assets" / "fonts" / "DejaVuSansMono-Bold.ttf"
)


def resolve_font_path(params: dict) -> str:
    return str(params.get("font_path") or BUNDLED_FONT)


class Font(Generator):
    """Glyph atlas: one frame per character, with advance metrics."""

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
                f"font: frames must be {len(chars)} (one per character in "
                f"'chars'), got {count}"
            )

        font_path = resolve_font_path(params)
        size = int(params.get("size", frame_px * 0.6))
        fill = tuple(int(c) for c in params.get("fill", [255, 255, 255]))
        try:
            face = ImageFont.truetype(font_path, size)
        except OSError as e:
            raise ValueError(f"font.font_path could not be loaded: {font_path} ({e})") from e

        pad = max(2, int(frame_px * 0.06))
        out: list[FrameData] = []
        for ch in chars:
            img = Image.new("RGBA", (frame_px, frame_px), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((pad, pad), ch, font=face, fill=fill + (255,))
            advance = round(face.getlength(ch))
            out.append(FrameData(id="", image=img, meta={"char": ch, "advance": advance}))
        return out

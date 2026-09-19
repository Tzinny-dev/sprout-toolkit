"""Generador `blob_walk`: hero blob pixel-art con ciclo de caminata.

El ciclo de 8 frames se construye a partir de la pose base añadiendo un
offset de fase ``t = (frame % 4)/4``: las piernas balancean con ``sin(tau*t)``
y el cuerpo respira/brinca. Las constantes micro están calibradas para
``frame_px = 64`` (paridad byte-a-byte con el prototipo de la demo); el cuerpo
escala proporcionalmente al tamaño pedido.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from .base import FrameData, Generator


class BlobWalk(Generator):
    id = "blob_walk"

    DEFAULTS = {
        "body": (244, 162, 97),
        "outline": (46, 36, 24),
        "belly": (226, 122, 63),
        "eye_white": (255, 255, 255),
        "eye": (30, 30, 30),
    }

    def _make_frame(self, f: int, size: int, p: dict) -> Image.Image:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx = size // 2
        base = int(size * 0.71875)      # 46 @64
        body_base = int(size * 0.3125)  # 20 @64
        t = (f % 4) / 4.0
        phase = math.sin(t * math.tau)
        body_r = body_base + int(1.5 * max(0, phase))
        body_cy = int(base - body_base - max(0, phase) * 2)

        leg = int(6 * abs(phase))
        leg_col = p["outline"]
        d.ellipse([cx - 3 - leg, base - 2, cx + 3 - leg, base + 6], fill=leg_col)
        d.ellipse([cx - 3 + leg, base - 2, cx + 3 + leg, base + 6], fill=leg_col)

        d.ellipse([cx - body_r, body_cy - body_r, cx + body_r, body_cy + body_r],
                  fill=p["body"], outline=p["outline"], width=2)
        d.ellipse([cx - body_r + 3, body_cy + 4, cx + body_r - 3, body_cy + body_r + 4],
                  fill=p["belly"])

        eye_dy = int(1.5 * math.sin(t * math.tau * 0.5))
        for ex in (+7, -7):
            d.ellipse([cx + ex - 4, body_cy + eye_dy - 4, cx + ex + 4, body_cy + eye_dy + 4],
                      fill=p["eye_white"])
            d.ellipse([cx + ex - 2, body_cy + eye_dy - 2, cx + ex + 2, body_cy + eye_dy + 2],
                      fill=p["eye"])
        d.arc([cx - 6, body_cy + 6, cx + 6, body_cy + 14], 20, 160,
              fill=p["outline"], width=2)
        return img

    def generate(
        self,
        seed: int,
        count: int,
        frame_px: int,
        params: dict,
        base: int = 0,
    ) -> list[FrameData]:
        p = dict(self.DEFAULTS)
        p.update({k: tuple(v) for k, v in params.items() if isinstance(v, list)})
        return [FrameData(id="", image=self._make_frame(i, frame_px, p))
                for i in range(count)]
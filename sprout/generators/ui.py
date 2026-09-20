"""``ui`` generator: interface elements (buttons, sliders, 9-patch panels).

Spec params (item.params):
    kind   : "button" | "slider" | "panel"  (default "button")
    fill   : [r, g, b]  fill color (optional override)
    outline: [r, g, b]  outline color (optional override)
    accent : [r, g, b]  slider progress color (optional override)

``button``: each frame is a state (normal/hover/pressed cycle by index).
``slider``: each frame is a progress step evenly spread over
[0, 1] (the knob advances with the index).
``panel``: requires ``frames=9`` (4 corners + 4 edges + 1 center, the same
pattern as ``autotile`` in ``terrain``); the 9 tiles are cropped from a
single rounded-rectangle to guarantee seamless assembly.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from .base import FrameData, Generator


def _clamp(v: float) -> int:
    return max(0, min(255, int(v)))


def _lighten(color: tuple[int, int, int], amt: float) -> tuple[int, int, int]:
    return tuple(_clamp(c + (255 - c) * amt) for c in color)  # type: ignore[return-value]


def _darken(color: tuple[int, int, int], amt: float) -> tuple[int, int, int]:
    return tuple(_clamp(c * (1 - amt)) for c in color)  # type: ignore[return-value]


class Ui(Generator):
    """Interface elements: button, slider, 9-patch panel."""

    id = "ui"

    KIND_DEFAULTS: dict[str, dict] = {
        "button": {"fill": (90, 130, 210), "outline": (40, 70, 130)},
        "slider": {"fill": (70, 70, 85), "outline": (40, 40, 50), "accent": (90, 200, 120)},
        "panel":  {"fill": (235, 230, 210), "outline": (120, 105, 80)},
    }

    PANEL_PATCHES = (
        "corner_tl", "edge_t", "corner_tr",
        "edge_l", "center", "edge_r",
        "corner_bl", "edge_b", "corner_br",
    )

    # ── button ────────────────────────────────────────────────────────────
    def _button(self, frame_px: int, state: int, p: dict) -> Image.Image:
        """state: 0=normal, 1=hover, 2=pressed."""
        img = Image.new("RGBA", (frame_px, frame_px), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        pad = frame_px * 0.08
        inset = frame_px * 0.05 if state == 2 else 0.0  # pressed: sinks in
        x0, y0 = pad + inset, pad + inset
        x1, y1 = frame_px - pad, frame_px - pad
        radius = frame_px * 0.22
        border = max(2, int(frame_px * 0.045))

        fill = p["fill"]
        if state == 1:
            fill = _lighten(fill, 0.12)
        elif state == 2:
            fill = _darken(fill, 0.12)

        d.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                            fill=fill, outline=p["outline"], width=border)
        if state != 2:
            # top highlight: suggests volume/bevel
            hl_pad = (x1 - x0) * 0.16
            d.rounded_rectangle(
                [x0 + hl_pad, y0 + hl_pad, x1 - hl_pad, y0 + (y1 - y0) * 0.4],
                radius=radius * 0.5, fill=_lighten(fill, 0.22) + (110,),
            )
        return img

    # ── slider ────────────────────────────────────────────────────────────
    def _slider(self, frame_px: int, t: float, p: dict) -> Image.Image:
        img = Image.new("RGBA", (frame_px, frame_px), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        margin = frame_px * 0.14
        track_h = frame_px * 0.18
        y0 = frame_px / 2 - track_h / 2
        y1 = frame_px / 2 + track_h / 2
        x0, x1 = margin, frame_px - margin
        radius = track_h / 2

        d.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                            fill=p["fill"], outline=p["outline"], width=1)

        knob_x = x0 + t * (x1 - x0)
        fill_pad = 1.0
        fx0, fy0, fx1, fy1 = x0 + fill_pad, y0 + fill_pad, knob_x, y1 - fill_pad
        fw, fh = fx1 - fx0, fy1 - fy0
        if fw >= 2.0 and fh >= 2.0:
            # extra -1 margin: avoids the edge case where PIL treats the
            # near-circular shape as a "pill" on both axes and produces an
            # intermediate rect with negative height (rounded_rectangle with
            # radius ~= exact half).
            fill_radius = max(0.0, min(radius - fill_pad, fw / 2 - 1, fh / 2 - 1))
            d.rounded_rectangle([fx0, fy0, fx1, fy1], radius=fill_radius,
                                fill=p["accent"])

        knob_r = frame_px * 0.16
        knob_color = _lighten(p["outline"], 0.55)
        d.ellipse(
            [knob_x - knob_r, frame_px / 2 - knob_r, knob_x + knob_r, frame_px / 2 + knob_r],
            fill=knob_color, outline=p["outline"], width=max(1, int(frame_px * 0.03)),
        )
        return img

    # ── panel (9-patch) ──────────────────────────────────────────────────
    def _panel(self, frame_px: int, p: dict) -> list[Image.Image]:
        big = frame_px * 3
        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        border = max(2, int(frame_px * 0.09))
        radius = frame_px * 0.5 - border  # stays within the corner cell
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=radius,
                            fill=p["fill"], outline=p["outline"], width=border)
        return [
            img.crop((col * frame_px, row * frame_px,
                      (col + 1) * frame_px, (row + 1) * frame_px))
            for row in range(3) for col in range(3)
        ]

    def generate(
        self,
        seed: int,
        count: int,
        frame_px: int,
        params: dict,
        base: int = 0,
    ) -> list[FrameData]:
        kind = params.get("kind", "button")
        if kind not in self.KIND_DEFAULTS:
            raise ValueError(
                f"invalid ui.kind '{kind}' "
                f"(available: {', '.join(sorted(self.KIND_DEFAULTS))})"
            )
        palette: dict = dict(self.KIND_DEFAULTS[kind])
        for key in ("fill", "outline", "accent"):
            v = params.get(key)
            if isinstance(v, list) and len(v) == 3:
                palette[key] = tuple(int(c) for c in v)

        if kind == "panel":
            if count != 9:
                raise ValueError(
                    f"ui.kind='panel' requires frames=9 (got {count})"
                )
            return [FrameData(id="", image=img) for img in self._panel(frame_px, palette)]

        if kind == "slider":
            n = max(2, count)
            return [
                FrameData(id="", image=self._slider(frame_px, i / (n - 1), palette))
                for i in range(n)
            ]

        # button
        return [
            FrameData(id="", image=self._button(frame_px, i % 3, palette))
            for i in range(count)
        ]

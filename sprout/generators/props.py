"""``props`` generator: static tile objects (rocks, bushes, chests,
mushrooms, flowers).

Each frame is a deterministic variant of the requested prop. The seed is
derived from ``seed * 1000 + base + i`` (same convention as ``terrain``), so
varying the slot in the spritesheet produces visual variation without
breaking determinism. Uses PIL primitives (ellipses, polygons, arcs) — no
continuous noise is required, so each variant is generated in O(1).

Spec parameters (item.params):
    kind   : "rock" | "bush" | "chest" | "mushroom" | "flower"  (default "rock")
    fill   : [r, g, b]  fill color (optional override)
    outline: [r, g, b]  outline color (optional override)

Each frame also carries an anchor point in ``meta["anchor"]`` — the point
where the object "touches the ground", in local frame pixels (same
system as ``w``/``h`` in the manifest). It is computed from the actual
rendered alpha bbox (not a fixed formula per kind), so it follows the
sprite's effective shape without manual per-kind maintenance.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from .base import FrameData, Generator


# ── Deterministic hash (identical to terrain.cell) ────────────────────────
def _cell(i: int, j: int, seed: int) -> float:
    h = (i * 374761393 + j * 668265263 + seed * 974711377) % 2**32
    return ((h >> 8) % 2**24) / 2**24


def _rnd(seed: int, i: int) -> float:
    """Value in [0, 1) used throughout for per-variant variation."""
    return _cell(i, 0, seed)


def _anchor_from_alpha(img: Image.Image) -> dict:
    """Ground contact point: horizontal center + bottom edge of the
    already-rendered alpha bbox. `getbbox()` returns (x0,y0,x1,y1) with
    x1/y1 exclusive, so y1 falls just below the last opaque pixel —
    a natural reading as "ground line". Empty frame -> center of the frame."""
    bbox = img.getchannel("A").getbbox()
    if bbox is None:
        return {"x": img.width / 2, "y": img.height / 2}
    x0, y0, x1, y1 = bbox
    return {"x": (x0 + x1) / 2, "y": y1}


class Props(Generator):
    """Static objects: rock, bush, chest, mushroom, flower."""

    id = "props"

    KIND_DEFAULTS: dict[str, dict] = {
        "rock":     {"fill": (120, 110, 125), "outline": (80, 75, 80)},
        "bush":     {"fill": (60, 140, 80),  "outline": (40, 95, 60)},
        "chest":    {"fill": (160, 110, 50),  "outline": (100, 70, 30)},
        "mushroom": {"fill": (200, 60, 60),   "outline": (140, 40, 40)},
        "flower":   {"fill": (240, 180, 80),  "outline": (200, 120, 50)},
    }

    # ── Renderers by kind ─────────────────────────────────────────────
    def _rock(self, d: ImageDraw.ImageDraw, cx: float, cy: float,
              r: float, vs: int, p: dict) -> None:
        """Irregular rock: polygon with radial jitter."""
        n = 8 + int(_rnd(vs, 1) * 4)
        pts = []
        for k in range(n):
            angle = 2 * math.pi * k / n
            jitter = 0.75 + _rnd(vs, k + 2) * 0.5
            ry = r * jitter
            px = cx + math.cos(angle) * ry * 0.85
            py = cy + math.sin(angle) * ry
            pts.append((px, py))
        d.polygon(pts, fill=p["fill"], outline=p["outline"])

    def _bush(self, d: ImageDraw.ImageDraw, cx: float, cy: float,
              r: float, vs: int, p: dict) -> None:
        """Bush: 3-5 overlapping ellipses."""
        n = 3 + int(_rnd(vs, 1) * 3)
        for k in range(n):
            angle = 2 * math.pi * k / n
            off_r = r * (0.3 + _rnd(vs, k + 2) * 0.4)
            bx = cx + math.cos(angle) * off_r
            by = cy + math.sin(angle) * off_r * 0.6
            er = r * (0.6 + _rnd(vs, k + 10) * 0.4)
            d.ellipse([bx - er, by - er, bx + er, by + er],
                      fill=p["fill"], outline=p["outline"])

    def _chest(self, d: ImageDraw.ImageDraw, cx: float, cy: float,
               r: float, vs: int, p: dict) -> None:
        """Chest: body + domed lid + lock + straps."""
        jitter = 1.0 + (_rnd(vs, 1) - 0.5) * 0.12  # +/-6% width
        w, h = r * 1.5 * jitter, r * 1.0
        x0, y0 = cx - w / 2, cy - h / 2
        x1, y1 = cx + w / 2, cy + h / 2
        lid_h = h * 0.42
        body_top = y0 + lid_h

        # body
        d.rectangle([x0, body_top, x1, y1], fill=p["fill"], outline=p["outline"])
        # domed lid (upper semicircle)
        d.pieslice([x0, y0, x1, y0 + 2 * lid_h], 180, 360,
                   fill=p["fill"], outline=p["outline"])
        # body/lid seam
        d.line([x0, body_top, x1, body_top], fill=p["outline"])
        # vertical straps
        for side in (-1, 1):
            bx = cx + side * w * 0.3
            d.line([bx, body_top, bx, y1], fill=p["outline"])
        # lock
        lw = max(3.0, w * 0.13)
        lh = max(4.0, h * 0.24)
        d.rectangle([cx - lw / 2, body_top - lh / 2, cx + lw / 2, body_top + lh / 2],
                    fill=p["outline"])
        d.ellipse([cx - lw * 0.22, body_top - lw * 0.22,
                   cx + lw * 0.22, body_top + lw * 0.22],
                  fill=(240, 225, 170))

    def _mushroom(self, d: ImageDraw.ImageDraw, cx: float, cy: float,
                  r: float, vs: int, p: dict) -> None:
        """Mushroom: cap with white spots + stem."""
        cap_r = r * 0.85
        d.ellipse([cx - cap_r, cy - cap_r, cx + cap_r, cy + cap_r],
                  fill=p["fill"], outline=p["outline"])
        stalk_w = r * 0.28
        stalk_h = r * 0.9
        d.rectangle([cx - stalk_w / 2, cy + cap_r, cx + stalk_w / 2, cy + cap_r + stalk_h],
                    fill=(220, 220, 205), outline=(155, 150, 140))
        n_spots = 4 + int(_rnd(vs, 1) * 5)
        for k in range(n_spots):
            angle = 2 * math.pi * k / n_spots + _rnd(vs, k) * 0.6
            sx = cx + math.cos(angle) * cap_r * 0.55
            sy = cy + math.sin(angle) * cap_r * 0.35
            sz = r * 0.13 * (0.7 + _rnd(vs, k + 2) * 0.6)
            d.ellipse([sx - sz, sy - sz, sx + sz, sy + sz], fill=(230, 230, 238))

    def _flower(self, d: ImageDraw.ImageDraw, cx: float, cy: float,
                r: float, vs: int, p: dict) -> None:
        """Flower: petals + center."""
        stalk_h = r * 1.1
        sw = max(2, int(r * 0.12))
        d.line([cx, cy - r * 0.3, cx, cy + stalk_h], fill=(45, 120, 45), width=sw)
        n_p = 5 + int(_rnd(vs, 1) * 4)
        for k in range(n_p):
            angle = 2 * math.pi * k / n_p
            dx = math.cos(angle) * r * 0.65
            dy = math.sin(angle) * r * 0.65
            pw = r * 0.55
            ph = r * 0.85 * (0.8 + _rnd(vs, k + 2) * 0.4)
            d.ellipse([cx + dx - pw / 2, cy + dy - ph / 2, cx + dx + pw / 2, cy + dy + ph / 2],
                      fill=p["fill"], outline=p["outline"])
        cr = r * 0.25
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(240, 220, 60), outline=(180, 160, 40))


    def generate(
        self,
        seed: int,
        count: int,
        frame_px: int,
        params: dict,
        base: int = 0,
    ) -> list[FrameData]:
        kind = params.get("kind", "rock")
        if kind not in self.KIND_DEFAULTS:
            raise ValueError(
                f"invalid props.kind '{kind}' "
                f"(available: {', '.join(sorted(self.KIND_DEFAULTS))})"
            )
        palette: dict = dict(self.KIND_DEFAULTS[kind])
        for k, v in params.items():
            if isinstance(v, list) and len(v) == 3 and k in ("fill", "outline"):
                palette[k] = tuple(int(c) for c in v)

        out: list[FrameData] = []
        for i in range(count):
            vs = (seed * 1000 + base + i) % 2**31
            img = Image.new("RGBA", (frame_px, frame_px), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            cx = cy = frame_px / 2
            r = frame_px * 0.35
            getattr(self, f"_{kind}")(d, cx, cy, r, vs, palette)
            out.append(FrameData(id="", image=img, meta={"anchor": _anchor_from_alpha(img)}))
        return out

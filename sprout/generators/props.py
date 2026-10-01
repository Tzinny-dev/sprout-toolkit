"""``props`` generator: static tile objects.

Classic kinds (v1): rocks, bushes, chests, mushrooms, flowers.
v3 object grammar: parametric food/object families with a ``form``
picker, covering flavor and thing catalog sets. The vocabulary is
data-driven (``assets/vocab/props.json``) so consumers can extend it
without forking the toolkit — see ``sprout/vocab.py``.

    fruit    apple | cherry | banana | grapes | strawberry
    sweet    candy | donut | cookie | cupcake | lollipop
    potion   bottle | flask | vial
    treasure coin | gem | star | ring
    tool     hammer | key | pencil | spoon | fork
    paper    book | scroll | envelope
    container bag | box

Each frame is a deterministic variant of the requested prop. The seed is
derived from ``seed * 1000 + base + i`` (same convention as ``terrain``), so
varying the slot in the spritesheet produces visual variation without
breaking determinism. Uses PIL primitives (ellipses, polygons, arcs) — no
continuous noise is required, so each variant is generated in O(1).

Spec parameters (item.params):
    kind   : any key of ``FORMS``  (default "rock")
    form   : "auto" | a form of the kind's vocabulary (v3 kinds only;
             "auto" picks a form per variant from the seed)
    fill   : [r, g, b]  fill color (optional override)
    accent : [r, g, b]  secondary color (v3 kinds)
    outline: [r, g, b]  outline color (optional override; v3 kinds derive
             it from ``fill`` via the shared ``darken(fill, .55)`` rule)

Each frame also carries an anchor point in ``meta["anchor"]`` — the point
where the object "touches the ground", in local frame pixels (same
system as ``w``/``h`` in the manifest). It is computed from the actual
rendered alpha bbox (not a fixed formula per kind), so it follows the
sprite's effective shape without manual per-kind maintenance.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from .. import palettes
from .. import vocab as vocab_mod
from .base import FrameData, Generator

TAU = math.tau


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


def _lighten(c: tuple, k: float = 0.45) -> tuple:
    """Scale an RGB triple toward white (mirror of ``palettes.darken``)."""
    return tuple(min(255, int(round(v + (255 - v) * k))) for v in c)


def _star_pts(cx: float, cy: float, ro: float, ri: float,
              n: int = 5) -> list[tuple[float, float]]:
    """Star polygon, tip pointing up (``n`` arms)."""
    pts = []
    for k in range(n * 2):
        a = -math.pi / 2 + math.pi * k / n
        rad = ro if k % 2 == 0 else ri
        pts.append((cx + math.cos(a) * rad, cy + math.sin(a) * rad))
    return pts


def _rrect(d: ImageDraw.ImageDraw, box: list, radius: float, **kw) -> None:
    """Rounded rect that degrades to a plain rect on thin boxes.

    PIL's ``rounded_rectangle`` raises in two float edge cases that small
    frames hit: an inner strip inverts when ``2*radius`` outgrows the box,
    and ``y0 + width - 1`` can round *below* ``y0`` for float coords.
    Quantizing the box to ints avoids both; when the radius no longer fits
    the box we draw a plain rectangle instead.
    """
    x0, y0, x1, y1 = (round(v) for v in box)
    rad = min(radius, (min(x1 - x0, y1 - y0) - 2) / 2)
    if rad < 1:
        d.rectangle([x0, y0, x1, y1], **kw)
    else:
        d.rounded_rectangle([x0, y0, x1, y1], radius=int(rad), **kw)


# kind -> allowed forms ("auto" always first). Formless v1 kinds only
# accept "auto" — the form param must not silently change their output.
# Loaded from assets/vocab/props.json so consumers can extend the grammar
# without forking the toolkit (see sprout/vocab.py).
_vocab = vocab_mod.load("props")
FORMS: dict[str, tuple[str, ...]] = {
    kind: tuple(forms) for kind, forms in _vocab["forms"].items()
}
FORMLESS = frozenset({"rock", "bush", "chest", "mushroom", "flower"})

# v3 palette per (kind, form): fill = dominant/tintable, accent = secondary.
# outline derives from fill via the shared rule unless overridden.
FORM_COLORS: dict[str, dict[str, dict[str, tuple]]] = _vocab["colors"]


class Props(Generator):
    """Static objects: 5 classic kinds + the v3 object grammar."""

    id = "props"

    PARAMS = frozenset({"kind", "form", "fill", "accent", "outline"})

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

    # ── v3 forms: fruit ────────────────────────────────────────────────
    def _leaf(self, d: ImageDraw.ImageDraw, lx: float, ly: float, lr: float,
              ang: float, fill: tuple, ow: int) -> None:
        pts = []
        for k in range(12):
            t = TAU * k / 12
            x, y = math.cos(t) * lr, math.sin(t) * lr * 0.55
            pts.append((lx + x * math.cos(ang) - y * math.sin(ang),
                        ly + x * math.sin(ang) + y * math.cos(ang)))
        d.polygon(pts, fill=fill, outline=palettes.outline_color(fill),
                  width=max(1, ow // 2))

    def _apple(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
               vs: int, p: dict, ow: int) -> None:
        d.ellipse([cx - 0.80 * r, cy - 0.72 * r, cx + 0.80 * r, cy + 0.84 * r],
                  fill=p["fill"], outline=p["outline"], width=ow)
        d.line([cx, cy - 0.70 * r, cx + 0.10 * r, cy - 1.0 * r],
               fill=(118, 84, 52), width=max(2, int(r * 0.09)))
        self._leaf(d, cx + 0.44 * r, cy - 0.90 * r, 0.30 * r, 0.55,
                   p["accent"], ow)
        d.ellipse([cx - 0.46 * r, cy - 0.50 * r, cx - 0.16 * r, cy - 0.22 * r],
                  fill=_lighten(p["fill"]))

    def _cherry(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
                vs: int, p: dict, ow: int) -> None:
        join = (cx + 0.04 * r, cy - 0.92 * r)
        balls = [(cx - 0.44 * r, cy + 0.30 * r, 0.46 * r),
                 (cx + 0.46 * r, cy + 0.42 * r, 0.42 * r)]
        for bx, by, br in balls:  # stems behind the fruit
            d.line([bx, by - br * 0.5, join[0], join[1]], fill=(118, 84, 52),
                   width=max(2, int(r * 0.07)))
        for bx, by, br in balls:
            d.ellipse([bx - br, by - br, bx + br, by + br], fill=p["fill"],
                      outline=p["outline"], width=ow)
            d.ellipse([bx - br * 0.6, by - br * 0.6, bx - br * 0.2,
                       by - br * 0.2], fill=_lighten(p["fill"]))
        self._leaf(d, cx + 0.36 * r, cy - 0.86 * r, 0.24 * r, -0.5,
                   p["accent"], ow)

    def _banana(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
                vs: int, p: dict, ow: int) -> None:
        n = 12
        outer, inner = [], []
        for k in range(n + 1):
            u = -1.0 + 2.0 * k / n
            x = cx + u * 0.88 * r
            y = cy + 0.42 * r - u * u * 0.78 * r
            thick = 0.30 * r * (0.35 + 0.65 * (1 - u * u))
            outer.append((x, y))
            inner.append((x, y - thick))
        d.polygon(outer + inner[::-1], fill=p["fill"], outline=p["outline"],
                  width=ow)
        for u in (-1.0, 1.0):
            tx, ty = cx + u * 0.86 * r, cy + 0.42 * r - 0.78 * r
            tr = 0.11 * r
            d.ellipse([tx - tr, ty - tr, tx + tr, ty + tr],
                      fill=palettes.darken(p["accent"]))

    def _grapes(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
                vs: int, p: dict, ow: int) -> None:
        gr = 0.24 * r
        for j, n in enumerate((4, 3, 2, 1)):
            y = cy - 0.36 * r + j * gr * 1.55
            for i in range(n):
                x = cx + (i - (n - 1) / 2) * gr * 1.7
                d.ellipse([x - gr, y - gr, x + gr, y + gr], fill=p["fill"],
                          outline=p["outline"], width=max(1, ow // 2))
        d.line([cx, cy - 0.58 * r, cx + 0.08 * r, cy - 0.96 * r],
               fill=(118, 84, 52), width=max(2, int(r * 0.08)))
        self._leaf(d, cx + 0.34 * r, cy - 0.88 * r, 0.24 * r, 0.5,
                   p["accent"], ow)

    def _strawberry(self, d: ImageDraw.ImageDraw, cx: float, cy: float,
                    r: float, vs: int, p: dict, ow: int) -> None:
        n = 8
        body = []
        for k in range(n + 1):
            a = math.pi + math.pi * k / n
            body.append((cx + math.cos(a) * 0.66 * r,
                         cy - 0.22 * r + math.sin(a) * 0.52 * r))
        body.append((cx, cy + 0.88 * r))
        d.polygon(body, fill=p["fill"], outline=p["outline"], width=ow)
        for row, halfw in enumerate((0.52 * r, 0.38 * r, 0.22 * r)):
            y = cy - 0.10 * r + row * 0.30 * r
            for i in range(3):
                x = cx + (i - 1) * halfw * 0.72
                s = max(1, int(r * 0.05))
                d.rectangle([x - s, y - s, x + s, y + s], fill=(250, 232, 150))
        for k in range(5):  # calyx fan
            ang = -math.pi / 2 + (k - 2) * 0.62
            lx = cx + math.cos(ang) * 0.34 * r
            ly = cy - 0.52 * r + math.sin(ang) * 0.20 * r
            self._leaf(d, lx, ly, 0.26 * r, ang, p["accent"], ow)
        d.line([cx, cy - 0.66 * r, cx + 0.04 * r, cy - 0.94 * r],
               fill=(118, 84, 52), width=max(2, int(r * 0.07)))

    # ── v3 forms: sweet ────────────────────────────────────────────────
    def _candy(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
               vs: int, p: dict, ow: int) -> None:
        acc_out = palettes.outline_color(p["accent"])
        for side in (-1, 1):
            x0, x1 = cx + side * 0.52 * r, cx + side * 1.0 * r
            lo, hi = min(x0, x1), max(x0, x1)
            d.polygon([(x0, cy - 0.30 * r), (x1, cy - 0.54 * r),
                       (x1, cy + 0.54 * r), (x0, cy + 0.30 * r)],
                      fill=p["accent"], outline=acc_out,
                      width=max(1, ow // 2))
            d.line([x0, cy - 0.30 * r, x0, cy + 0.30 * r], fill=p["outline"],
                   width=max(1, ow // 2))
        _rrect(d, [cx - 0.60 * r, cy - 0.44 * r, cx + 0.60 * r,
                   cy + 0.44 * r], 0.20 * r, fill=p["fill"],
               outline=p["outline"], width=ow)
        d.line([cx - 0.30 * r, cy - 0.18 * r, cx + 0.30 * r, cy - 0.18 * r],
               fill=_lighten(p["fill"]), width=max(1, int(r * 0.12)))

    def _donut(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
               vs: int, p: dict, ow: int) -> None:
        R = 0.88 * r
        d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=p["fill"],
                  outline=p["outline"], width=ow)
        ir = 0.80 * r
        box = [cx - ir, cy - ir - 0.06 * r, cx + ir, cy + ir - 0.06 * r]
        d.pieslice(box, 165, 375, fill=p["accent"])
        d.arc(box, 165, 375, fill=palettes.outline_color(p["accent"]),
              width=max(1, ow))
        for k in range(6):  # sprinkles on the icing
            a = math.pi * (1.10 + 0.78 * _rnd(vs, 20 + k))
            rad = ir * (0.40 + 0.42 * _rnd(vs, 30 + k))
            sx, sy = cx + math.cos(a) * rad, cy - 0.06 * r + math.sin(a) * rad
            ex, ey = sx + math.cos(a + 1.3) * 0.10 * r, sy + math.sin(a + 1.3) * 0.10 * r
            d.line([sx, sy, ex, ey], fill=(255, 255, 255),
                   width=max(2, int(r * 0.07)))
        rh = 0.26 * r
        d.ellipse([cx - rh - ow, cy - rh - ow, cx + rh + ow, cy + rh + ow],
                  fill=p["outline"])
        d.ellipse([cx - rh, cy - rh, cx + rh, cy + rh], fill=(0, 0, 0, 0))

    def _cookie(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
                vs: int, p: dict, ow: int) -> None:
        R = 0.86 * r
        d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=p["fill"],
                  outline=p["outline"], width=ow)
        n = 7
        for k in range(n):
            a = TAU * k / n + _rnd(vs, 20 + k) * 0.7
            rad = R * (0.25 + 0.45 * _rnd(vs, 30 + k))
            sx, sy = cx + math.cos(a) * rad, cy + math.sin(a) * rad
            cr = r * 0.10
            d.ellipse([sx - cr, sy - cr, sx + cr, sy + cr], fill=p["accent"])

    def _cupcake(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
                 vs: int, p: dict, ow: int) -> None:
        acc_out = palettes.outline_color(p["accent"])
        d.polygon([(cx - 0.62 * r, cy + 0.85 * r), (cx - 0.44 * r, cy + 0.02 * r),
                   (cx + 0.44 * r, cy + 0.02 * r), (cx + 0.62 * r, cy + 0.85 * r)],
                  fill=p["accent"], outline=acc_out, width=ow)
        dark = palettes.darken(p["accent"], 0.8)
        for k in (-1, 0, 1):
            d.line([cx + k * 0.26 * r, cy + 0.06 * r,
                    cx + k * 0.40 * r, cy + 0.82 * r], fill=dark,
                   width=max(1, int(r * 0.07)))
        for ty, trx, try_ in ((cy + 0.06 * r, 0.56 * r, 0.24 * r),
                              (cy - 0.22 * r, 0.45 * r, 0.22 * r),
                              (cy - 0.48 * r, 0.30 * r, 0.18 * r)):
            d.ellipse([cx - trx, ty - try_, cx + trx, ty + try_],
                      fill=p["fill"], outline=p["outline"],
                      width=max(1, ow // 2))
        cr = 0.13 * r
        d.ellipse([cx - cr, cy - 0.66 * r - cr, cx + cr, cy - 0.66 * r + cr],
                  fill=(224, 64, 64), outline=(150, 40, 40),
                  width=max(1, ow // 2))

    def _lollipop(self, d: ImageDraw.ImageDraw, cx: float, cy: float,
                  r: float, vs: int, p: dict, ow: int) -> None:
        _rrect(d, [cx - 0.07 * r, cy + 0.20 * r, cx + 0.07 * r,
                   cy + 1.05 * r], 0.06 * r,
               fill=(240, 230, 210), outline=(180, 168, 148),
               width=max(1, ow // 2))
        R = 0.62 * r
        ccy = cy - 0.18 * r
        d.ellipse([cx - R, ccy - R, cx + R, ccy + R], fill=p["fill"],
                  outline=p["outline"], width=ow)
        pts = []
        for k in range(48):
            t = k / 47
            a = TAU * 2.4 * t
            rad = R * 0.84 * t
            pts.append((cx + math.cos(a) * rad, ccy + math.sin(a) * rad))
        d.line(pts, fill=p["accent"], width=max(2, int(r * 0.13)),
               joint="curve")

    # ── v3 forms: potion ───────────────────────────────────────────────
    def _bottle(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
                vs: int, p: dict, ow: int) -> None:
        d.rectangle([cx - 0.19 * r, cy - 0.68 * r, cx + 0.19 * r, cy - 0.05 * r],
                    fill=p["accent"])
        d.rectangle([cx - 0.23 * r, cy - 0.94 * r, cx + 0.23 * r, cy - 0.62 * r],
                    fill=(150, 108, 70), outline=(100, 72, 44),
                    width=max(1, ow // 2))
        body = [cx - 0.58 * r, cy - 0.12 * r, cx + 0.58 * r, cy + 0.95 * r]
        _rrect(d, body, 0.18 * r, fill=p["accent"])
        d.rectangle([cx - 0.48 * r, cy + 0.18 * r, cx + 0.48 * r, cy + 0.87 * r],
                    fill=p["fill"])
        d.line([cx - 0.44 * r, cy + 0.20 * r, cx + 0.44 * r, cy + 0.20 * r],
               fill=palettes.darken(p["fill"], 0.85), width=max(1, ow // 2))
        _rrect(d, body, 0.18 * r, outline=p["outline"], width=ow)
        d.rectangle([cx - 0.19 * r, cy - 0.68 * r, cx + 0.19 * r, cy - 0.10 * r],
                    outline=p["outline"], width=max(1, ow // 2))

    def _flask(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
               vs: int, p: dict, ow: int) -> None:
        hw0, hw1 = 0.17 * r, 0.78 * r
        y_top, y_bot = cy - 0.35 * r, cy + 0.90 * r
        d.rectangle([cx - hw0, cy - 0.82 * r, cx + hw0, y_top + 0.05 * r],
                    fill=p["accent"])
        d.rectangle([cx - 0.21 * r, cy - 1.0 * r, cx + 0.21 * r, cy - 0.78 * r],
                    fill=(150, 108, 70), outline=(100, 72, 44),
                    width=max(1, ow // 2))
        body = [(cx - hw0, y_top), (cx - hw1, y_bot), (cx + hw1, y_bot),
                (cx + hw0, y_top)]
        d.polygon(body, fill=p["accent"])
        y0 = cy + 0.25 * r
        t = (y0 - y_top) / (y_bot - y_top)
        hw_y = hw0 + (hw1 - hw0) * t
        d.polygon([(cx - hw_y, y0), (cx - hw1, y_bot), (cx + hw1, y_bot),
                   (cx + hw_y, y0)], fill=p["fill"])
        d.line([cx - hw_y, y0, cx + hw_y, y0],
               fill=palettes.darken(p["fill"], 0.85), width=max(1, ow // 2))
        for k, bx in enumerate((-0.35, 0.3)):
            br = r * (0.06 + 0.03 * k)
            by = y0 + (0.3 + 0.35 * k) * r
            d.ellipse([cx + bx * r - br, by - br, cx + bx * r + br, by + br],
                      fill=_lighten(p["fill"], 0.5))
        d.polygon(body, outline=p["outline"], width=ow)
        d.rectangle([cx - hw0, cy - 0.82 * r, cx + hw0, y_top],
                    outline=p["outline"], width=max(1, ow // 2))

    def _vial(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
              vs: int, p: dict, ow: int) -> None:
        d.rectangle([cx - 0.24 * r, cy - 0.80 * r, cx + 0.24 * r, cy - 0.55 * r],
                    fill=(150, 108, 70), outline=(100, 72, 44),
                    width=max(1, ow // 2))
        body = [cx - 0.30 * r, cy - 0.58 * r, cx + 0.30 * r, cy + 0.95 * r]
        _rrect(d, body, 0.12 * r, fill=p["accent"])
        d.rectangle([cx - 0.22 * r, cy + 0.15 * r, cx + 0.22 * r, cy + 0.86 * r],
                    fill=p["fill"])
        for k, (bx, by) in enumerate(((-0.06, 0.35), (0.07, 0.55), (-0.02, 0.72))):
            br = r * 0.05
            d.ellipse([cx + bx * r - br, cy + by * r - br,
                       cx + bx * r + br, cy + by * r + br],
                      fill=_lighten(p["fill"], 0.5))
        _rrect(d, body, 0.12 * r, outline=p["outline"], width=ow)

    # ── v3 forms: treasure ─────────────────────────────────────────────
    def _coin(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
              vs: int, p: dict, ow: int) -> None:
        R = 0.85 * r
        d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=p["fill"],
                  outline=p["outline"], width=ow)
        rim = 0.64 * R
        d.ellipse([cx - rim, cy - rim, cx + rim, cy + rim],
                  outline=palettes.darken(p["fill"], 0.72),
                  width=max(1, ow // 2))
        emb = 0.42 * R
        d.polygon(_star_pts(cx, cy, emb, emb * 0.44),
                  fill=palettes.darken(p["fill"], 0.78))

    def _gem(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
             vs: int, p: dict, ow: int) -> None:
        pts = [(cx - 0.55 * r, cy - 0.55 * r), (cx + 0.55 * r, cy - 0.55 * r),
               (cx + 0.78 * r, cy - 0.15 * r), (cx, cy + 0.90 * r),
               (cx - 0.78 * r, cy - 0.15 * r)]
        d.polygon(pts, fill=p["fill"], outline=p["outline"], width=ow)
        lite = _lighten(p["fill"], 0.4)
        d.line([cx - 0.78 * r, cy - 0.15 * r, cx + 0.78 * r, cy - 0.15 * r],
               fill=palettes.darken(p["fill"], 0.72), width=max(1, ow // 2))
        for x in (-0.55, -0.18, 0.18, 0.55):
            d.line([cx + x * r, cy - 0.55 * r, cx + x * 0.35 * r, cy - 0.15 * r],
                   fill=lite, width=max(1, ow // 2))
        d.line([cx, cy - 0.15 * r, cx, cy + 0.90 * r], fill=lite,
               width=max(1, ow // 2))
        d.polygon([(cx - 0.42 * r, cy - 0.46 * r), (cx - 0.08 * r, cy - 0.46 * r),
                   (cx - 0.22 * r, cy - 0.22 * r), (cx - 0.52 * r, cy - 0.22 * r)],
                  fill=lite)

    def _star(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
              vs: int, p: dict, ow: int) -> None:
        d.polygon(_star_pts(cx, cy, 0.92 * r, 0.42 * r), fill=p["fill"],
                  outline=p["outline"], width=ow)
        cr = 0.14 * r
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr],
                  fill=_lighten(p["fill"], 0.5))

    def _ring(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
              vs: int, p: dict, ow: int) -> None:
        band_y = cy + 0.24 * r
        bo = 0.62 * r
        d.ellipse([cx - bo, band_y - bo, cx + bo, band_y + bo], fill=p["fill"],
                  outline=p["outline"], width=ow)
        bi = 0.42 * r
        d.ellipse([cx - bi - ow, band_y - bi - ow, cx + bi + ow, band_y + bi + ow],
                  fill=p["outline"])
        d.ellipse([cx - bi, band_y - bi, cx + bi, band_y + bi], fill=(0, 0, 0, 0))
        gem = [(cx, cy - 0.85 * r), (cx + 0.27 * r, cy - 0.55 * r),
               (cx, cy - 0.30 * r), (cx - 0.27 * r, cy - 0.55 * r)]
        d.polygon(gem, fill=p["accent"], outline=palettes.outline_color(p["accent"]),
                  width=ow)
        d.polygon([(cx, cy - 0.80 * r), (cx + 0.10 * r, cy - 0.58 * r),
                   (cx - 0.06 * r, cy - 0.55 * r)], fill=_lighten(p["accent"], 0.5))

    # ── v3 forms: tool ─────────────────────────────────────────────────
    def _hammer(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
                vs: int, p: dict, ow: int) -> None:
        acc_out = palettes.outline_color(p["accent"])
        _rrect(d, [cx - 0.10 * r, cy - 0.35 * r, cx + 0.10 * r,
                   cy + 0.98 * r], 0.08 * r, fill=p["accent"],
               outline=acc_out, width=ow)
        _rrect(d, [cx - 0.75 * r, cy - 0.82 * r, cx + 0.75 * r,
                   cy - 0.32 * r], 0.10 * r, fill=p["fill"],
               outline=p["outline"], width=ow)
        d.line([cx + 0.44 * r, cy - 0.76 * r, cx + 0.44 * r, cy - 0.38 * r],
               fill=palettes.darken(p["fill"], 0.78), width=max(1, ow // 2))

    def _key(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
             vs: int, p: dict, ow: int) -> None:
        br = 0.40 * r
        by = cy - 0.55 * r
        d.ellipse([cx - br, by - br, cx + br, by + br], fill=p["fill"],
                  outline=p["outline"], width=ow)
        hr = 0.18 * r
        d.ellipse([cx - hr - ow, by - hr - ow, cx + hr + ow, by + hr + ow],
                  fill=p["outline"])
        d.ellipse([cx - hr, by - hr, cx + hr, by + hr], fill=(0, 0, 0, 0))
        d.rectangle([cx - 0.10 * r, cy - 0.32 * r, cx + 0.10 * r, cy + 0.95 * r],
                    fill=p["fill"], outline=p["outline"], width=ow)
        for ty in (0.38 * r, 0.68 * r):
            d.rectangle([cx + 0.10 * r, cy + ty - 0.10 * r,
                         cx + 0.38 * r, cy + ty + 0.10 * r], fill=p["fill"],
                        outline=p["outline"], width=max(1, ow // 2))

    def _pencil(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
                vs: int, p: dict, ow: int) -> None:
        W = 0.17 * r
        d.rectangle([cx - W, cy - 0.64 * r, cx + W, cy + 0.50 * r],
                    fill=p["fill"], outline=p["outline"], width=ow)
        d.polygon([(cx - W, cy + 0.50 * r), (cx + W, cy + 0.50 * r),
                   (cx, cy + 0.85 * r)], fill=(230, 202, 158),
                  outline=p["outline"], width=max(1, ow // 2))
        d.polygon([(cx - 0.06 * r, cy + 0.72 * r), (cx + 0.06 * r, cy + 0.72 * r),
                   (cx, cy + 0.95 * r)], fill=(48, 44, 42))
        d.rectangle([cx - W, cy - 0.78 * r, cx + W, cy - 0.62 * r],
                    fill=(178, 184, 194), outline=(120, 126, 136),
                    width=max(1, ow // 2))
        d.rectangle([cx - W, cy - 0.98 * r, cx + W, cy - 0.76 * r],
                    fill=p["accent"], outline=palettes.outline_color(p["accent"]),
                    width=max(1, ow // 2))
        d.line([cx - 0.06 * r, cy - 0.56 * r, cx - 0.06 * r, cy + 0.42 * r],
               fill=_lighten(p["fill"], 0.4), width=max(1, int(r * 0.08)))

    def _spoon(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
               vs: int, p: dict, ow: int) -> None:
        W = 0.09 * r
        _rrect(d, [cx - W, cy - 0.05 * r, cx + W, cy + 0.98 * r],
               W, fill=p["fill"], outline=p["outline"], width=ow)
        bw, bh = 0.36 * r, 0.50 * r
        top = cy - 0.98 * r
        d.ellipse([cx - bw, top, cx + bw, top + 2 * bh], fill=p["fill"],
                  outline=p["outline"], width=ow)
        iw, ih = bw * 0.6, bh * 0.6
        d.ellipse([cx - iw, top + bh - ih, cx + iw, top + bh + ih],
                  fill=_lighten(p["fill"], 0.3))

    def _fork(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
              vs: int, p: dict, ow: int) -> None:
        W = 0.09 * r
        _rrect(d, [cx - W, cy - 0.15 * r, cx + W, cy + 0.98 * r],
               W, fill=p["fill"], outline=p["outline"], width=ow)
        hw = 0.38 * r
        d.rectangle([cx - hw, cy - 0.98 * r, cx + hw, cy - 0.45 * r],
                    fill=p["fill"], outline=p["outline"], width=ow)
        gap = 0.05 * r
        for k in (-1, 1):
            gx = cx + k * 0.17 * r
            d.rectangle([gx - gap, cy - 1.04 * r, gx + gap, cy - 0.62 * r],
                        fill=(0, 0, 0, 0))

    # ── tool: sword ─────────────────────────────────────────────────────
    def _sword(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
               vs: int, p: dict, ow: int) -> None:
        # blade (tapered diamond)
        tip, guard = cy - 0.98 * r, cy - 0.30 * r
        bw = 0.11 * r
        d.polygon([(cx, tip), (cx + bw, guard), (cx, guard + 0.14 * r),
                   (cx - bw, guard)], fill=p["fill"],
                  outline=p["outline"], width=max(1, ow // 2))
        d.line([cx, tip + 0.08 * r, cx, guard + 0.02 * r],
               fill=_lighten(p["fill"], 0.45), width=max(1, int(r * 0.06)))
        # crossguard
        _rrect(d, [cx - 0.62 * r, guard, cx + 0.62 * r, guard + 0.16 * r],
               0.06 * r, fill=p["accent"],
               outline=palettes.outline_color(p["accent"]), width=max(1, ow // 2))
        # grip
        _rrect(d, [cx - 0.07 * r, guard + 0.14 * r, cx + 0.07 * r,
                   cy + 0.86 * r], 0.05 * r, fill=palettes.darken(p["accent"], 0.55),
               outline=p["outline"], width=max(1, ow // 2))
        # pommel
        d.ellipse([cx - 0.14 * r, cy + 0.84 * r, cx + 0.14 * r, cy + 1.10 * r],
                  fill=p["accent"], outline=p["outline"], width=max(1, ow // 2))

    # ── tool: shield ────────────────────────────────────────────────────
    def _shield(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
                vs: int, p: dict, ow: int) -> None:
        top, bot = cy - 0.90 * r, cy + 0.96 * r
        w = 0.66 * r
        body = [(cx - w, top + 0.10 * r), (cx + w, top + 0.10 * r),
                (cx + w, cy + 0.20 * r), (cx, bot), (cx - w, cy + 0.20 * r)]
        d.polygon(body, fill=p["fill"], outline=p["outline"], width=ow)
        # vertical band
        d.line([cx, top + 0.16 * r, cx, cy + 0.14 * r],
               fill=p["accent"], width=max(1, int(r * 0.10)))
        # horizontal band
        d.line([cx - w + 0.06 * r, cy - 0.36 * r, cx + w - 0.06 * r, cy - 0.36 * r],
               fill=p["accent"], width=max(1, int(r * 0.08)))
        # boss (center stud)
        d.ellipse([cx - 0.16 * r, cy - 0.52 * r, cx + 0.16 * r, cy - 0.20 * r],
                  fill=_lighten(p["accent"], 0.30), outline=p["outline"],
                  width=max(1, ow // 2))

    # ── tool: axe ───────────────────────────────────────────────────────
    def _axe(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
             vs: int, p: dict, ow: int) -> None:
        # haft
        _rrect(d, [cx - 0.06 * r, cy - 0.96 * r, cx + 0.06 * r, cy + 0.96 * r],
               0.05 * r, fill=p["accent"],
               outline=palettes.outline_color(p["accent"]), width=max(1, ow // 2))
        # head: broad wedge spanning both sides of the haft (centered)
        hl, hr_ = 0.52 * r, 0.66 * r
        top, bot = cy - 0.84 * r, cy + 0.06 * r
        blade = [(cx - hr_, top), (cx + hr_, top),
                 (cx + hl, cy - 0.20 * r), (cx + hr_, bot),
                 (cx - hr_, bot), (cx - hl, cy - 0.20 * r)]
        d.polygon(blade, fill=p["fill"], outline=p["outline"], width=max(1, ow // 2))
        d.line([cx - 0.34 * r, top + 0.06 * r, cx - 0.46 * r, cy - 0.20 * r],
               fill=_lighten(p["fill"], 0.40), width=max(1, int(r * 0.05)))
        d.line([cx + 0.34 * r, top + 0.06 * r, cx + 0.46 * r, cy - 0.20 * r],
               fill=_lighten(p["fill"], 0.40), width=max(1, int(r * 0.05)))

    # ── tool: bow ───────────────────────────────────────────────────────
    def _bow(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
             vs: int, p: dict, ow: int) -> None:
        # curved limbs as a polyline arc (thick so it reads at 64px)
        steps = 16
        thick = max(2, int(0.14 * r))
        # arc centered on frame: bulge left, tips right
        pts = [(cx + 0.30 * r - 0.52 * r * t * t, cy + t * 0.92 * r)
               for t in (-1 + 2 * k / steps for k in range(steps + 1))]
        d.line(pts, fill=p["fill"], width=thick, joint="curve")
        d.line(pts, fill=palettes.outline_color(p["fill"]),
               width=max(1, ow // 2), joint="curve")
        # string (taut, connecting the tips)
        d.line([pts[0][0], pts[0][1], cx + 0.34 * r, cy, pts[-1][0], pts[-1][1]],
               fill=_lighten(p["accent"], 0.25), width=max(1, int(r * 0.05)))

    # ── tool: pickaxe ───────────────────────────────────────────────────
    def _pickaxe(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
                 vs: int, p: dict, ow: int) -> None:
        # handle
        _rrect(d, [cx - 0.07 * r, cy - 0.40 * r, cx + 0.07 * r, cy + 0.96 * r],
               0.05 * r, fill=p["accent"],
               outline=palettes.outline_color(p["accent"]), width=max(1, ow // 2))
        # thick double-curved head
        thick = max(2, int(0.15 * r))
        for side in (-1, 1):
            d.line([cx, cy - 0.60 * r,
                    cx + side * 0.36 * r, cy - 0.88 * r,
                    cx + side * 0.68 * r, cy - 0.66 * r],
                   fill=p["fill"], width=thick, joint="curve")
            d.line([cx, cy - 0.60 * r,
                    cx + side * 0.36 * r, cy - 0.88 * r,
                    cx + side * 0.68 * r, cy - 0.66 * r],
                   fill=palettes.outline_color(p["fill"]),
                   width=max(1, ow // 2), joint="curve")
        # collar
        _rrect(d, [cx - 0.13 * r, cy - 0.68 * r, cx + 0.13 * r, cy - 0.48 * r],
               0.04 * r, fill=p["fill"], outline=p["outline"], width=max(1, ow // 2))

    # ── tool: wrench ────────────────────────────────────────────────────
    def _wrench(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
                vs: int, p: dict, ow: int) -> None:
        # shaft
        _rrect(d, [cx - 0.08 * r, cy - 0.30 * r, cx + 0.08 * r, cy + 0.92 * r],
               0.06 * r, fill=p["fill"], outline=p["outline"], width=max(1, ow // 2))
        # open head (jaw) at top
        jw, jh = 0.30 * r, 0.26 * r
        top = cy - 0.94 * r
        d.arc([cx - jw, top, cx + jw, top + 2 * jh], 150, 30,
              fill=p["fill"], width=max(2, int(0.16 * r)))
        d.arc([cx - jw, top, cx + jw, top + 2 * jh], 150, 30,
              fill=p["outline"], width=max(1, ow // 2))
        # jaw notch (cut-out opening)
        d.rectangle([cx - jw * 0.42, top - 0.04 * r, cx + jw * 0.42, top + jh * 0.7],
                    fill=(0, 0, 0, 0))
        # ring head at bottom
        rr = 0.16 * r
        d.ellipse([cx - rr, cy + 0.86 * r, cx + rr, cy + 1.22 * r],
                  fill=p["fill"], outline=p["outline"], width=max(1, ow // 2))
        d.ellipse([cx - rr * 0.45, cy + 0.86 * r + rr * 0.55,
                   cx + rr * 0.45, cy + 1.22 * r - rr * 0.55],
                  fill=(0, 0, 0, 0))

    # ── v3 forms: paper ────────────────────────────────────────────────
    def _book(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
              vs: int, p: dict, ow: int) -> None:
        cover = [cx - 0.72 * r, cy - 0.55 * r, cx + 0.72 * r, cy + 0.68 * r]
        d.rectangle(cover, fill=p["fill"])
        d.rectangle([cx + 0.50 * r, cy - 0.48 * r, cx + 0.72 * r, cy + 0.60 * r],
                    fill=p["accent"])
        d.rectangle([cx - 0.72 * r, cy - 0.55 * r, cx - 0.50 * r, cy + 0.68 * r],
                    fill=palettes.darken(p["fill"], 0.78))
        d.rectangle([cx - 0.36 * r, cy - 0.16 * r, cx + 0.36 * r, cy + 0.06 * r],
                    fill=_lighten(p["fill"], 0.35))
        d.rectangle(cover, outline=p["outline"], width=ow)
        d.line([cx - 0.50 * r, cy - 0.55 * r, cx - 0.50 * r, cy + 0.68 * r],
               fill=p["outline"], width=max(1, ow // 2))

    def _scroll(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
                vs: int, p: dict, ow: int) -> None:
        sheet = [cx - 0.66 * r, cy - 0.52 * r, cx + 0.66 * r, cy + 0.52 * r]
        d.rectangle(sheet, fill=p["fill"], outline=p["outline"],
                    width=max(1, ow // 2))
        for k in range(3):
            y = cy - 0.22 * r + k * 0.24 * r
            d.line([cx - 0.44 * r, y, cx + 0.44 * r, y],
                   fill=palettes.darken(p["fill"], 0.68),
                   width=max(1, int(r * 0.06)))
        for y0, y1 in ((cy - 0.78 * r, cy - 0.46 * r), (cy + 0.46 * r, cy + 0.78 * r)):
            _rrect(d, [cx - 0.76 * r, y0, cx + 0.76 * r, y1], 0.14 * r,
                   fill=p["accent"],
                   outline=palettes.outline_color(p["accent"]), width=ow)

    def _envelope(self, d: ImageDraw.ImageDraw, cx: float, cy: float,
                  r: float, vs: int, p: dict, ow: int) -> None:
        ev = [cx - 0.78 * r, cy - 0.50 * r, cx + 0.78 * r, cy + 0.50 * r]
        d.rectangle(ev, fill=p["fill"], outline=p["outline"], width=ow)
        d.polygon([(cx - 0.78 * r, cy - 0.50 * r), (cx, cy + 0.08 * r),
                   (cx + 0.78 * r, cy - 0.50 * r)], fill=_lighten(p["fill"], 0.25),
                  outline=p["outline"], width=ow)
        sx, sy = cx + 0.42 * r, cy + 0.16 * r
        d.rectangle([sx, sy, sx + 0.24 * r, sy + 0.24 * r], fill=p["accent"],
                    outline=palettes.outline_color(p["accent"]),
                    width=max(1, ow // 2))

    # ── v3 forms: container ────────────────────────────────────────────
    def _bag(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
             vs: int, p: dict, ow: int) -> None:
        d.ellipse([cx - 0.64 * r, cy - 0.30 * r, cx + 0.64 * r, cy + 0.95 * r],
                  fill=p["fill"], outline=p["outline"], width=ow)
        d.polygon([(cx - 0.32 * r, cy - 0.20 * r), (cx - 0.18 * r, cy - 0.62 * r),
                   (cx + 0.18 * r, cy - 0.62 * r), (cx + 0.32 * r, cy - 0.20 * r)],
                  fill=p["fill"], outline=p["outline"], width=ow)
        d.ellipse([cx - 0.26 * r, cy - 0.98 * r, cx + 0.26 * r, cy - 0.52 * r],
                  fill=p["fill"], outline=p["outline"], width=ow)
        _rrect(d, [cx - 0.36 * r, cy - 0.58 * r, cx + 0.36 * r,
                   cy - 0.42 * r], 0.06 * r, fill=p["accent"],
               outline=palettes.outline_color(p["accent"]),
               width=max(1, ow // 2))

    def _box(self, d: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
             vs: int, p: dict, ow: int) -> None:
        d.rectangle([cx - 0.60 * r, cy - 0.10 * r, cx + 0.60 * r, cy + 0.80 * r],
                    fill=p["fill"], outline=p["outline"], width=ow)
        d.rectangle([cx - 0.68 * r, cy - 0.52 * r, cx + 0.68 * r, cy - 0.06 * r],
                    fill=_lighten(p["fill"], 0.2), outline=p["outline"],
                    width=ow)
        d.rectangle([cx - 0.10 * r, cy - 0.52 * r, cx + 0.10 * r, cy + 0.80 * r],
                    fill=p["accent"])
        acc_out = palettes.outline_color(p["accent"])
        for x0, x1 in ((cx - 0.44 * r, cx - 0.08 * r), (cx + 0.08 * r, cx + 0.44 * r)):
            d.ellipse([x0, cy - 0.78 * r, x1, cy - 0.50 * r], fill=p["accent"],
                      outline=acc_out, width=max(1, ow // 2))
        d.rectangle([cx - 0.10 * r, cy - 0.66 * r, cx + 0.10 * r,
                     cy - 0.54 * r], fill=p["accent"],
                    outline=acc_out, width=max(1, ow // 2))


    def generate(
        self,
        seed: int,
        count: int,
        frame_px: int,
        params: dict,
        base: int = 0,
    ) -> list[FrameData]:
        kind = params.get("kind", "rock")
        if kind not in FORMS:
            raise ValueError(
                f"invalid props.kind '{kind}' "
                f"(available: {', '.join(sorted(FORMS))})"
            )
        form = str(params.get("form", "auto"))
        vocab = FORMS[kind]
        if form not in vocab:
            raise ValueError(
                f"invalid props.form '{form}' for kind '{kind}' "
                f"(available: {', '.join(vocab)})"
            )
        overrides = {
            k: tuple(int(c) for c in v)
            for k, v in params.items()
            if k in ("fill", "accent", "outline")
            and isinstance(v, list) and len(v) == 3
        }
        ow = palettes.outline_width(frame_px)

        out: list[FrameData] = []
        for i in range(count):
            vs = (seed * 1000 + base + i) % 2**31
            if kind in FORMLESS:
                chosen = None
                p = dict(self.KIND_DEFAULTS[kind])
            else:
                options = vocab[1:]
                chosen = (
                    form if form != "auto"
                    else options[int(_rnd(vs, 15) * len(options)) % len(options)]
                )
                p = dict(FORM_COLORS[kind][chosen])
            p.update(overrides)
            if "outline" not in p:
                p["outline"] = palettes.outline_color(p["fill"])
            img = Image.new("RGBA", (frame_px, frame_px), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            cx = cy = frame_px / 2
            r = frame_px * 0.35
            if chosen is None:
                getattr(self, f"_{kind}")(d, cx, cy, r, vs, p)
            else:
                getattr(self, f"_{chosen}")(d, cx, cy, r, vs, p, ow)
            out.append(FrameData(id="", image=img, meta={"anchor": _anchor_from_alpha(img)}))
        return out

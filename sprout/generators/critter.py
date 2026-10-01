"""``critter`` generator: parametric 2D creatures.

Five body plans, each drawn side-view facing right (``bug`` is top-view,
the only angle where beetles read at 64 px):

    quadruped   body + 4 legs + head with ears + tail
    bird        egg body + crested head + beak + fan tail + thin legs
    fish        oval body + dorsal/fan fins, no legs
    reptile     low body + splayed legs + flat head + long tapered tail
    bug         segmented body + head + antennae + 6 legs (top view)

Anatomy (ears / snout / tail / legs / wings / pattern and size ratios) derives
from ``seed * 1000 + base`` — the item's slot, never the frame index — so every
frame of an item is the *same* species; only the idle pose changes
(breathing sine + a one-frame blink). Part params force a value; the
default ``"auto"`` lets the seed pick among the archetype's options.

Tint-ready by default: the base palette is a neutral warm gray ramp
(``fill``/``belly``/``far``), so ``tint: shade`` re-hues it without
muddying. ``fill`` / ``outline`` / ``belly`` / ``beak`` override per spec.

The outline follows the shared rule (``palettes.outline_width``):
``max(1, frame_px // 32)`` — 2 px at 64, 4 px at 128.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from .. import palettes
from .base import FrameData, Generator
from .props import _anchor_from_alpha, _rnd

TAU = math.tau

ARCHETYPES = ("quadruped", "bird", "fish", "reptile", "bug")
EARS = ("auto", "none", "round", "pointy", "long")
SNOUT = ("auto", "none", "short", "long", "beak")
TAIL = ("auto", "none", "short", "long", "bushy", "fan")
LEGS = ("auto", "none", "stubby", "thin", "splayed")
WINGS = ("auto", "none", "small", "spread")
PATTERNS = ("auto", "none", "spots", "stripes", "patch")
FACINGS = ("right", "left")

# Seed picks per archetype when the part param is "auto".
_AUTO: dict[str, dict[str, tuple[str, ...]]] = {
    "quadruped": {"ears": ("round", "pointy"), "snout": ("short", "long"),
                  "tail": ("short", "bushy"), "legs": ("stubby",),
                  "wings": ("none",),
                  "pattern": ("none", "spots", "stripes", "patch")},
    "bird": {"ears": ("none",), "snout": ("beak",), "tail": ("fan",),
             "legs": ("thin",), "wings": ("small", "spread"),
             "pattern": ("none", "stripes")},
    "fish": {"ears": ("none",), "snout": ("none",), "tail": ("fan",),
             "legs": ("none",), "wings": ("none",),
             "pattern": ("none", "spots", "stripes")},
    "reptile": {"ears": ("none",), "snout": ("short",), "tail": ("long", "short"),
                "legs": ("splayed",), "wings": ("none",),
                "pattern": ("none", "stripes", "patch")},
    "bug": {"ears": ("none",), "snout": ("none",), "tail": ("none",),
            "legs": ("thin",), "wings": ("none", "small"),
            # the bug already draws its own mirrored elytra spots
            "pattern": ("none",)},
}

_PART_SALTS = {"ears": 11, "snout": 12, "tail": 13, "legs": 14, "wings": 15,
               "pattern": 16}


def _anatomy(vs: int, archetype: str) -> dict:
    """One creature's fixed proportions (no frame index — stable per item)."""
    auto = _AUTO[archetype]

    def pick(part: str) -> str:
        opts = auto[part]
        return opts[int(_rnd(vs, _PART_SALTS[part]) * len(opts)) % len(opts)]

    return {
        "ears": pick("ears"),
        "snout": pick("snout"),
        "tail": pick("tail"),
        "legs": pick("legs"),
        "wings": pick("wings"),
        "pattern": pick("pattern"),
        "body_len": 0.90 + _rnd(vs, 31) * 0.26,
        "body_h": 0.90 + _rnd(vs, 32) * 0.24,
        "head": 0.90 + _rnd(vs, 33) * 0.26,
        "leg_len": 0.85 + _rnd(vs, 34) * 0.35,
        "tail_len": 0.80 + _rnd(vs, 35) * 0.50,
        "ear_scale": 0.85 + _rnd(vs, 36) * 0.40,
    }


def _leg_w(S: float) -> int:
    """Leg/limb thickness: scales with the frame (2 px at 64)."""
    return max(1, int(round(S * 0.031)))


class Critter(Generator):
    """Parametric creatures: archetypes + composable parts + idle frames."""

    id = "critter"

    PARAMS = frozenset({
        "archetype", "facing",
        "ears", "snout", "tail", "legs", "wings", "pattern",
        "fill", "outline", "belly", "eye", "eye_white", "beak",
    })

    DEFAULTS = {
        "fill": (216, 210, 200),       # neutral warm gray (tint-ready)
        "outline": (48, 44, 40),
        "belly": (242, 238, 230),
        "eye_white": (255, 255, 255),
        "eye": (32, 30, 28),
        "beak": (240, 170, 60),
    }

    # ── Shared face pieces ─────────────────────────────────────────────
    def _body_marks(self, d: ImageDraw.ImageDraw, bcx: float, bcy: float,
                    a: float, b: float, anat: dict, p: dict) -> None:
        """Markings inside the body ellipse, in the ``far`` shade.

        Every shape is bounded by the ellipse's own half-height at that
        offset (``b * sqrt(1 - (dx/a)^2)``) instead of a mask, so a marking
        can never bleed past the outline at any frame size.
        """
        pattern = anat["pattern"]
        if pattern == "none":
            return
        vs = anat["_vs"]

        def half_h(dx: float) -> float:
            t = 1.0 - (dx / a) ** 2
            return b * math.sqrt(t) if t > 0.0 else 0.0

        if pattern == "stripes":
            n = 3 + int(_rnd(vs, 80) * 2)          # 3..4 bands
            band = a * 0.13
            for k in range(n):
                dx = -a * 0.60 + (k + 0.5) * (a * 1.20 / n)
                hh = half_h(dx) * 0.78
                if hh <= 0.0:
                    continue
                d.rectangle([bcx + dx - band / 2, bcy - hh,
                             bcx + dx + band / 2, bcy + hh], fill=p["far"])
        elif pattern == "spots":
            n = 3 + int(_rnd(vs, 81) * 3)          # 3..5 dots
            for k in range(n):
                dx = -a * 0.58 + _rnd(vs, 82 + k) * a * 1.16
                hh = half_h(dx)
                # clamp the dot so it fits the curve, then keep it on the
                # upper band: the belly is drawn *after* the marks and would
                # otherwise swallow every dot on a wide, flat body
                sr = min(a, b) * 0.13
                if hh <= sr:
                    continue
                sr = min(sr, hh * 0.55)
                sy = bcy - hh * 0.42 + (_rnd(vs, 100 + k) - 0.5) * 0.7 * (hh - sr)
                d.ellipse([bcx + dx - sr, sy - sr, bcx + dx + sr, sy + sr],
                          fill=p["far"])
        elif pattern == "patch":
            # a saddle over the rear third, inscribed in the body's own curve
            px = -a * 0.42
            ph = half_h(px) * 0.82
            pw = a * 0.48
            d.ellipse([bcx + px - pw / 2, bcy - ph / 2,
                       bcx + px + pw / 2, bcy + ph / 2], fill=p["far"])

    def _eye(self, d: ImageDraw.ImageDraw, x: float, y: float, r: float,
             p: dict, ow: int, blink: bool) -> None:
        if blink:
            d.line([x - r, y, x + r, y], fill=p["outline"],
                   width=max(1, int(round(r * 0.9))))
            return
        # No outline on the white: an outlined ring reads as a hole at 64 px
        # (the pupil alone carries the expression, same as blob_walk).
        d.ellipse([x - r, y - r, x + r, y + r], fill=p["eye_white"])
        pr = r * 0.62
        px = x + r * 0.25  # pupil biased toward the facing side
        d.ellipse([px - pr, y - pr, px + pr, y + pr], fill=p["eye"])

    def _ears(self, d: ImageDraw.ImageDraw, hx: float, hy: float, hr: float,
              kind: str, anat: dict, p: dict, ow: int) -> None:
        s = anat["ear_scale"]
        if kind == "round":
            for side in (-1, 1):
                ex = hx + side * hr * 0.66
                ey = hy - hr * 0.92
                er = hr * 0.50 * s
                d.ellipse([ex - er, ey - er, ex + er, ey + er],
                          fill=p["fill"], outline=p["outline"], width=ow)
        elif kind == "pointy":
            w, h = hr * 0.42, hr * 1.05 * s
            for side in (-1, 1):
                bx = hx + side * hr * 0.62
                by = hy - hr * 0.45
                d.polygon([(bx - w, by), (bx + w, by),
                           (bx + side * hr * 0.30, by - h)],
                          fill=p["fill"], outline=p["outline"], width=ow)
        elif kind == "long":
            for side in (-1, 1):
                ex = hx + side * hr * 0.48
                ew, eh = hr * 0.40, hr * 1.35 * s
                d.ellipse([ex - ew / 2, hy - hr * 0.55 - eh, ex + ew / 2,
                           hy - hr * 0.55],
                          fill=p["fill"], outline=p["outline"], width=ow)

    def _snout(self, d: ImageDraw.ImageDraw, hx: float, hy: float, hr: float,
               kind: str, p: dict, ow: int) -> None:
        if kind == "long":
            # muzzle: fill only — an outlined ellipse inside the head reads
            # as a hole, not as a snout; keep it inside the head silhouette
            # (head half-width at dy=0.24hr is ~0.97hr).
            mw, mh = hr * 0.70, hr * 0.50
            mx, my = hx + hr * 0.55, hy + hr * 0.24
            d.ellipse([mx - mw / 2, my - mh / 2, mx + mw / 2, my + mh / 2],
                      fill=p["belly"])
            nr = max(1.5, hr * 0.18)
            d.ellipse([mx + mw * 0.30 - nr, my - nr,
                       mx + mw * 0.30 + nr, my + nr], fill=p["outline"])
        elif kind == "short":
            nr = max(1.5, hr * 0.20)
            d.ellipse([hx + hr * 0.72 - nr, hy + hr * 0.28 - nr,
                       hx + hr * 0.72 + nr, hy + hr * 0.28 + nr],
                      fill=p["outline"])
        elif kind == "beak":
            bk = p["beak"]
            d.polygon([(hx + hr * 0.62, hy - hr * 0.22),
                       (hx + hr * 0.62, hy + hr * 0.38),
                       (hx + hr * 0.62 + hr * 1.05, hy + hr * 0.10)],
                      fill=bk, outline=p["outline"], width=max(1, ow // 2))

    def _tail(self, d: ImageDraw.ImageDraw, bx: float, by: float, S: float,
              kind: str, anat: dict, p: dict, ow: int) -> None:
        tl = anat["tail_len"]
        if kind == "short":
            # stub going back and slightly down (upward = reads as a fin)
            d.polygon([(bx + S * 0.02, by - S * 0.12),
                       (bx - S * 0.16 * tl, by - S * 0.05 * tl),
                       (bx - S * 0.15 * tl, by + S * 0.07),
                       (bx + S * 0.02, by + S * 0.14)],
                      fill=p["fill"], outline=p["outline"], width=ow)
        elif kind == "bushy":
            tr = S * 0.15 * tl
            tx = bx - tr * 0.55
            d.ellipse([tx - tr, by - tr, tx + tr, by + tr],
                      fill=p["fill"], outline=p["outline"], width=ow)
        elif kind == "long":
            length = S * 0.46 * tl
            n, r0 = 8, S * 0.055 * anat["body_h"]
            top, bot = [], []
            for k in range(n + 1):
                t = k / n
                x = bx - t * length
                y = by - math.sin(t * math.pi * 0.55) * S * 0.10 * tl
                r = max(0.6, r0 * (1.0 - t * 0.88))
                top.append((x, y - r))
                bot.append((x, y + r))
            d.polygon(top + list(reversed(bot)), fill=p["fill"],
                      outline=p["outline"], width=ow)
        elif kind == "fan":
            for dy, ln in ((-0.16, 0.95), (0.0, 1.15), (0.16, 0.95)):
                d.polygon([(bx + S * 0.02, by + dy * S * 0.22),
                           (bx - S * 0.24 * tl * ln, by + (dy - 0.10) * S * tl),
                           (bx - S * 0.24 * tl * ln, by + (dy + 0.14) * S * tl)],
                          fill=p["far"], outline=p["outline"],
                          width=max(1, ow // 2))

    # ── Archetypes ────────────────────────────────────────────────────
    def _quadruped(self, d, S, anat, p, ow, breath, blink) -> None:
        cx, ground = S * 0.5, S * 0.86
        body_w = S * 0.48 * anat["body_len"]
        body_h = S * 0.32 * anat["body_h"] * (1 + 0.035 * breath)
        leg_h = S * 0.16 * anat["leg_len"]
        bob = -1.6 * (S / 64) * breath
        bcx = cx - S * 0.03
        bcy = ground - leg_h - body_h / 2 + bob
        bbot = bcy + body_h / 2

        if anat["tail"] != "none":
            self._tail(d, bcx - body_w / 2 + S * 0.03, bcy - body_h * 0.10,
                       S, anat["tail"], anat, p, ow)

        # far legs (behind the body, darker); wide enough that the interior
        # fill survives the 2 px outline (a narrow rect reads as a dark bar)
        fw = S * 0.10
        for side in (-1, 1):
            x = bcx + side * body_w * 0.30 - fw * 0.55
            d.rounded_rectangle([x - fw / 2, bbot - S * 0.04, x + fw / 2, ground],
                                radius=fw / 2, fill=p["far"],
                                outline=p["outline"], width=ow)

        d.ellipse([bcx - body_w / 2, bcy - body_h / 2, bcx + body_w / 2,
                   bcy + body_h / 2], fill=p["fill"], outline=p["outline"],
                  width=ow)
        self._body_marks(d, bcx, bcy, body_w / 2, body_h / 2, anat, p)
        bw, bh = body_w * 0.62, body_h * 0.56
        d.ellipse([bcx - bw / 2, bcy + body_h * 0.14 - bh / 2,
                   bcx + bw / 2, bcy + body_h * 0.14 + bh / 2], fill=p["belly"])

        # head
        hr = S * 0.135 * anat["head"]
        hx = bcx + body_w / 2 - hr * 0.30
        hy = bcy - body_h / 2 + hr * 0.55
        self._ears(d, hx, hy, hr, anat["ears"], anat, p, ow)
        d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=p["fill"],
                  outline=p["outline"], width=ow)
        self._snout(d, hx, hy, hr, anat["snout"], p, ow)
        self._eye(d, hx + hr * 0.34, hy - hr * 0.12, max(2.0, hr * 0.40), p,
                  ow, blink)

        # near legs (front of the body)
        for side in (-1, 1):
            x = bcx + side * body_w * 0.30 + fw * 0.55
            d.rounded_rectangle([x - fw / 2, bbot - S * 0.04, x + fw / 2, ground],
                                radius=fw / 2, fill=p["fill"],
                                outline=p["outline"], width=ow)

    def _bird(self, d, S, anat, p, ow, breath, blink) -> None:
        cx, ground = S * 0.5, S * 0.86
        body_w = S * 0.40 * anat["body_len"]
        body_h = S * 0.34 * anat["body_h"] * (1 + 0.03 * breath)
        leg_h = S * 0.14 * anat["leg_len"]
        bob = -1.4 * (S / 64) * breath
        bcx = cx - S * 0.02
        bcy = ground - leg_h - body_h / 2 + bob
        btop = bcy - body_h / 2

        if anat["tail"] != "none":
            self._tail(d, bcx - body_w / 2 + S * 0.03, bcy - body_h * 0.05,
                       S, anat["tail"], anat, p, ow)

        hr = S * 0.115 * anat["head"]
        hx = bcx + body_w * 0.32
        hy = btop - hr * 0.35

        # thin legs
        lw = _leg_w(S)
        for side in (-1, 1):
            x = bcx + side * body_w * 0.22
            d.line([x, bcy + body_h * 0.30, x, ground - lw * 0.4],
                   fill=p["outline"], width=lw)
            d.line([x, ground - lw * 0.4, x + lw * 1.4, ground - lw * 0.4],
                   fill=p["outline"], width=lw)

        d.ellipse([bcx - body_w / 2, bcy - body_h / 2, bcx + body_w / 2,
                   bcy + body_h / 2], fill=p["fill"], outline=p["outline"],
                  width=ow)
        self._body_marks(d, bcx, bcy, body_w / 2, body_h / 2, anat, p)

        # wing: small, low on the back — a big centered oval reads as a
        # second body, not a wing
        if anat["wings"] != "none":
            grow = 1.2 if anat["wings"] == "spread" else 1.0
            ww, wh = body_w * 0.42 * grow, body_h * 0.40 * grow
            wx = bcx - body_w * 0.12
            wy = bcy + body_h * 0.10
            d.ellipse([wx - ww / 2, wy - wh / 2, wx + ww / 2, wy + wh / 2],
                      fill=p["far"], outline=p["outline"], width=max(1, ow // 2))

        d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=p["fill"],
                  outline=p["outline"], width=ow)
        self._snout(d, hx, hy, hr, anat["snout"], p, ow)
        self._eye(d, hx + hr * 0.28, hy - hr * 0.14, max(2.0, hr * 0.40), p,
                  ow, blink)

    def _fish(self, d, S, anat, p, ow, breath, blink) -> None:
        cx = S * 0.5
        cy = S * 0.52
        body_w = S * 0.50 * anat["body_len"]
        body_h = S * 0.34 * anat["body_h"] * (1 + 0.04 * breath)
        bcx = cx + S * 0.04
        left = bcx - body_w / 2

        if anat["tail"] != "none":
            self._tail(d, left + S * 0.02, cy, S, anat["tail"], anat, p, ow)

        # dorsal fin
        top = cy - body_h / 2
        d.polygon([(bcx - S * 0.06, top + S * 0.02),
                   (bcx + body_w * 0.22, top + S * 0.02),
                   (bcx - S * 0.02, top - S * 0.11 * anat["tail_len"])],
                  fill=p["far"], outline=p["outline"], width=max(1, ow // 2))

        d.ellipse([bcx - body_w / 2, cy - body_h / 2, bcx + body_w / 2,
                   cy + body_h / 2], fill=p["fill"], outline=p["outline"],
                  width=ow)
        self._body_marks(d, bcx, cy, body_w / 2, body_h / 2, anat, p)

        # pectoral fin: a small fin sweeping back-down (an ellipse here
        # reads as a spot punched through the body)
        d.polygon([(bcx + body_w * 0.04, cy + body_h * 0.10),
                   (bcx - body_w * 0.20, cy + body_h * 0.42),
                   (bcx + body_w * 0.14, cy + body_h * 0.34)],
                  fill=p["far"], outline=p["outline"], width=max(1, ow // 2))

        # gill line
        gr = body_h * 0.34
        gx = bcx + body_w * 0.22
        d.arc([gx - gr * 0.5, cy - gr, gx + gr * 0.5, cy + gr], -65, 65,
              fill=p["outline"], width=max(1, ow // 2))

        # mouth
        mr = max(1.5, S * 0.03)
        d.arc([bcx + body_w / 2 - mr * 2, cy + body_h * 0.10,
               bcx + body_w / 2, cy + body_h * 0.10 + mr * 2], 20, 70,
              fill=p["outline"], width=max(1, ow // 2))

        self._eye(d, bcx + body_w * 0.30, cy - body_h * 0.18,
                  max(2.0, S * 0.055), p, ow, blink)

    def _reptile(self, d, S, anat, p, ow, breath, blink) -> None:
        cx, ground = S * 0.5, S * 0.86
        body_w = S * 0.52 * anat["body_len"]
        body_h = S * 0.24 * anat["body_h"] * (1 + 0.03 * breath)
        leg_h = S * 0.11 * anat["leg_len"]
        bob = -1.2 * (S / 64) * breath
        bcx = cx - S * 0.02
        bcy = ground - leg_h - body_h / 2 + bob
        bbot = bcy + body_h / 2

        if anat["tail"] != "none":
            self._tail(d, bcx - body_w / 2 + S * 0.02, bcy, S, anat["tail"],
                       anat, p, ow)

        # Two visible legs per side (front + back), wide enough to show fill.
        # Four evenly spaced stubs per side read as a picket fence.
        fw = S * 0.09
        for xf in (-0.30, 0.30):
            x = bcx + xf * body_w - fw * 0.55
            d.rounded_rectangle([x - fw / 2, bbot - S * 0.03, x + fw / 2, ground],
                                radius=fw / 2, fill=p["far"],
                                outline=p["outline"], width=max(1, ow // 2))

        d.ellipse([bcx - body_w / 2, bcy - body_h / 2, bcx + body_w / 2,
                   bcy + body_h / 2], fill=p["fill"], outline=p["outline"],
                  width=ow)
        self._body_marks(d, bcx, bcy, body_w / 2, body_h / 2, anat, p)
        bw, bh = body_w * 0.60, body_h * 0.50
        d.ellipse([bcx - bw / 2, bcy + body_h * 0.12 - bh / 2,
                   bcx + bw / 2, bcy + body_h * 0.12 + bh / 2], fill=p["belly"])

        # flat head, attached at the front (not on top)
        hrw = S * 0.115 * anat["head"]
        hrh = S * 0.075 * anat["head"]
        hx = bcx + body_w / 2 - hrw * 0.15
        hy = bcy - body_h * 0.18
        d.ellipse([hx - hrw, hy - hrh, hx + hrw, hy + hrh], fill=p["fill"],
                  outline=p["outline"], width=ow)
        self._snout(d, hx, hy, hrw, anat["snout"], p, ow)
        self._eye(d, hx + hrw * 0.30, hy - hrh * 0.45, max(2.0, S * 0.048),
                  p, ow, blink)

        # near splayed legs
        for xf in (-0.30, 0.30):
            x = bcx + xf * body_w + fw * 0.55
            d.rounded_rectangle([x - fw / 2, bbot - S * 0.03, x + fw / 2, ground],
                                radius=fw / 2, fill=p["fill"],
                                outline=p["outline"], width=max(1, ow // 2))

    def _bug(self, d, S, anat, p, ow, breath, blink) -> None:
        cx = S * 0.5
        cy = S * 0.58
        ab_w = S * 0.44 * anat["body_len"]
        ab_h = S * 0.46 * anat["body_h"] * (1 + 0.03 * breath)
        hr = S * 0.105 * anat["head"]
        hx, hy = cx, cy - ab_h * 0.48 - hr * 0.45
        lw = _leg_w(S)

        # legs (3 per side)
        for side in (-1, 1):
            for k, t in enumerate((-0.34, 0.0, 0.34)):
                rx = cx + side * ab_w * 0.44
                ry = cy + t * ab_h * 0.8
                d.line([rx, ry, rx + side * S * 0.11, ry + (k - 1) * S * 0.05],
                       fill=p["outline"], width=lw)

        # antennae
        for side in (-1, 1):
            pts = [(hx + side * hr * 0.35, hy - hr * 0.75),
                   (hx + side * hr * 1.15, hy - hr * 1.55),
                   (hx + side * hr * 1.75, hy - hr * 1.85)]
            d.line(pts, fill=p["outline"], width=lw, joint="curve")

        d.ellipse([cx - ab_w / 2, cy - ab_h / 2, cx + ab_w / 2, cy + ab_h / 2],
                  fill=p["fill"], outline=p["outline"], width=ow)
        self._body_marks(d, cx, cy, ab_w / 2, ab_h / 2, anat, p)

        # elytra seam / spots (top view: spots mirror across the spine)
        if anat["wings"] == "small":
            d.line([cx, cy - ab_h * 0.42, cx, cy + ab_h * 0.44],
                   fill=p["outline"], width=max(1, ow // 2))
        n_pairs = 2 + int(_rnd(anat["_vs"], 41) * 2)  # 2..3 mirrored pairs
        for k in range(n_pairs):
            jx = _rnd(anat["_vs"], 42 + k)
            jy = _rnd(anat["_vs"], 50 + k)
            sr = S * 0.045 * (0.8 + _rnd(anat["_vs"], 60 + k) * 0.5)
            ox = ab_w * (0.16 + 0.16 * jx)
            oy = (-ab_h * 0.28 + (k + 0.5) * (ab_h * 0.56 / n_pairs)
                  + (jy - 0.5) * ab_h * 0.12)
            for side in (-1, 1):
                sx, sy = cx + side * ox, cy + oy
                d.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=p["far"])
        if _rnd(anat["_vs"], 70) > 0.45:
            sr = S * 0.045 * (0.8 + _rnd(anat["_vs"], 71) * 0.5)
            sy = cy - ab_h * 0.05
            d.ellipse([cx - sr, sy - sr, cx + sr, sy + sr], fill=p["far"])

        d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=p["fill"],
                  outline=p["outline"], width=ow)
        er = max(1.5, hr * 0.26)
        for side in (-1, 1):
            ex = hx + side * hr * 0.50
            ey = hy - hr * 0.25
            if blink:
                d.line([ex - er, ey, ex + er, ey], fill=p["outline"],
                       width=max(1, int(round(er))))
            else:
                d.ellipse([ex - er, ey - er, ex + er, ey + er], fill=p["eye"])

    # ── Entry point ───────────────────────────────────────────────────
    def generate(self, seed, count, frame_px, params, base=0) -> list[FrameData]:
        archetype = str(params.get("archetype", "quadruped"))
        if archetype not in ARCHETYPES:
            raise ValueError(
                f"invalid critter.archetype '{archetype}' "
                f"(available: {', '.join(ARCHETYPES)})"
            )
        facing = str(params.get("facing", "right"))
        if facing not in FACINGS:
            raise ValueError(
                f"invalid critter.facing '{facing}' "
                f"(available: {', '.join(FACINGS)})"
            )

        vs = (seed * 1000 + base) % 2**31
        anat = _anatomy(vs, archetype)
        anat["_vs"] = vs
        for part, allowed in (("ears", EARS), ("snout", SNOUT), ("tail", TAIL),
                              ("legs", LEGS), ("wings", WINGS),
                              ("pattern", PATTERNS)):
            val = str(params.get(part, "auto"))
            if val not in allowed:
                raise ValueError(
                    f"invalid critter.{part} '{val}' "
                    f"(available: {', '.join(allowed)})"
                )
            if val != "auto":
                anat[part] = val

        p = dict(self.DEFAULTS)
        p.update({k: tuple(v) for k, v in params.items()
                  if isinstance(v, list) and len(v) == 3})
        p["far"] = palettes.darken(p["fill"], 0.72)
        ow = palettes.outline_width(frame_px)

        blink_frame = int(_rnd(vs, 90) * count) if count >= 4 else -1
        renderer = getattr(self, f"_{archetype}")

        out: list[FrameData] = []
        for i in range(count):
            breath = math.sin((i / count) * TAU)
            img = Image.new("RGBA", (frame_px, frame_px), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            renderer(d, float(frame_px), anat, p, ow, breath, i == blink_frame)
            if facing == "left":
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            out.append(FrameData(id="", image=img,
                                 meta={"anchor": _anchor_from_alpha(img)}))
        return out

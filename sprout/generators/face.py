"""``face`` generator: parametric emotion faces.

Head shape + eyes + mouth + brows + extras (blush, sweat, tears, anger
mark), driven by a ``mood`` preset that resolves the four parts to a
coherent combination — explicit part params override the preset:

    mood=happy          -> eyes=open  mouth=smile brows=none extras=none
    mood=happy + mouth=frown         -> grin-free happy eyes, frown mouth

Sixteen moods cover the emotion vocabulary; ``auto`` lets the seed pick.
Anatomy (head shape, feature scale) derives from ``seed * 1000 + base`` —
the item's slot, never the frame index — so every frame of an item is the
same face. With ``frames >= 4`` and blinkable eyes
(``open``/``wide``/``wink``/``heart``) exactly one frame is a blink; the
other frames are byte-identical (an emotion icon must not wobble).

Outline follows the shared rule (``palettes.outline_width``); colors are
plain roles (``fill``/``outline``/``eye``/``accent``/``drop``/``mouth``)
and accept ``params.palette``.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from .. import palettes
from .. import vocab as vocab_mod
from .base import FrameData, Generator
from .props import _anchor_from_alpha, _rnd

TAU = math.tau

# Loaded from assets/vocab/face.json so consumers can extend the emotion
# vocabulary without forking the toolkit (see sprout/vocab.py).
_vocab = vocab_mod.load("face")

HEADS = tuple(_vocab["heads"])
EYES = tuple(_vocab["eyes"])
MOUTHS = tuple(_vocab["mouths"])
BROWS = tuple(_vocab["brows"])
EXTRAS = tuple(_vocab["extras"])

BLINKABLE = ("open", "wide", "wink", "heart")

# name -> coherent parts combination
MOODS: dict[str, dict[str, str]] = _vocab["moods"]

# head silhouettes: round = radius, others = half extents (fractions of S)
_HEAD_SHAPES = {
    "round":  {"r": 0.34},
    "oval":   {"hw": 0.29, "hh": 0.36},
    "square": {"hw": 0.32, "hh": 0.31, "radius": 0.14},
    "wide":   {"hw": 0.38, "hh": 0.28},
}

EYE_DX = 0.145    # eye offset from center, fraction of S
EYE_DY = -0.045
BROW_DY = -0.155
MOUTH_DY = 0.145


def _pick(opts: tuple[str, ...], vs: int, salt: int) -> str:
    return opts[int(_rnd(vs, salt) * len(opts)) % len(opts)]


def _anatomy(vs: int) -> dict:
    """One face's fixed proportions (no frame index — stable per item)."""
    return {
        "head": _pick(HEADS[1:], vs, 11),
        "eye_scale": 0.92 + _rnd(vs, 31) * 0.16,
        "mouth_scale": 0.92 + _rnd(vs, 32) * 0.16,
    }


class Face(Generator):
    """Parametric emotion faces: mood presets + per-part overrides."""

    id = "face"

    PARAMS = frozenset({
        "mood", "head", "eyes", "mouth", "brows", "extras",
        "fill", "outline", "eye", "eye_white", "accent",
        "drop", "tongue", "anger",
    })

    DEFAULTS = {
        "fill": (245, 227, 201),      # neutral head tone (tint-friendly)
        "outline": (70, 54, 48),
        "eye": (38, 34, 32),
        "eye_white": (255, 255, 255),
        "accent": (244, 138, 150),    # blush / heart eyes
        "drop": (120, 190, 245),      # sweat / tears
        "mouth": (92, 54, 50),
        "tongue": (240, 128, 128),
        "anger": (222, 70, 58),
    }

    # ── Head ──────────────────────────────────────────────────────────
    def _head(self, d: ImageDraw.ImageDraw, S: float, shape: str, p: dict,
              ow: int, cx: float, cy: float) -> tuple[float, float]:
        spec = _HEAD_SHAPES[shape]
        if "r" in spec:
            r = spec["r"] * S
            d.ellipse([cx - r, cy - r, cx + r, cy + r],
                      fill=p["fill"], outline=p["outline"], width=ow)
            return r, r
        hw, hh = spec["hw"] * S, spec["hh"] * S
        if shape == "square":
            d.rounded_rectangle([cx - hw, cy - hh, cx + hw, cy + hh],
                                radius=spec["radius"] * S, fill=p["fill"],
                                outline=p["outline"], width=ow)
        else:
            d.ellipse([cx - hw, cy - hh, cx + hw, cy + hh],
                      fill=p["fill"], outline=p["outline"], width=ow)
        return hw, hh

    # ── Eyes ──────────────────────────────────────────────────────────
    def _eye(self, d: ImageDraw.ImageDraw, x: float, y: float, S: float,
             style: str, es: float, p: dict, ow: int) -> None:
        if style == "closed":
            ln = 0.105 * S * es
            d.line([x - ln, y, x + ln, y], fill=p["eye"], width=max(2, ow))
            return
        if style == "happy":  # ^ ^ (upper arc)
            rx, ry = 0.060 * S * es, 0.050 * S * es
            d.arc([x - rx, y - ry, x + rx, y + ry], 180, 360,
                  fill=p["eye"], width=max(2, ow))
            return
        if style == "x":
            r = 0.050 * S * es
            d.line([x - r, y - r, x + r, y + r], fill=p["eye"], width=ow)
            d.line([x - r, y + r, x + r, y - r], fill=p["eye"], width=ow)
            return
        if style == "heart":
            dxh, rh = 0.030 * S * es, 0.034 * S * es
            for side in (-1, 1):
                lx = x + side * dxh
                ly = y - 0.020 * S * es
                d.ellipse([lx - rh, ly - rh, lx + rh, ly + rh],
                          fill=p["accent"])
            d.polygon([(x - 0.058 * S * es, y - 0.002 * S * es),
                       (x + 0.058 * S * es, y - 0.002 * S * es),
                       (x, y + 0.070 * S * es)], fill=p["accent"])
            # carve the top notch back to head skin so the heart reads
            d.polygon([(x, y - 0.072 * S * es),
                       (x - 0.016 * S * es, y - 0.026 * S * es),
                       (x + 0.016 * S * es, y - 0.026 * S * es)],
                      fill=p["fill"])
            return
        # open / wide (drawn as a pair by the caller; single eye here)
        if style == "wide":
            rx, ry, pr = 0.075 * S * es, 0.090 * S * es, 0.030 * S * es
        else:
            rx, ry, pr = 0.055 * S * es, 0.068 * S * es, 0.034 * S * es
        d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=p["eye_white"])
        d.ellipse([x - pr, y - pr + ry * 0.1, x + pr, y + pr + ry * 0.1],
                  fill=p["eye"])

    def _blink_line(self, d: ImageDraw.ImageDraw, x: float, y: float,
                    S: float, es: float, p: dict, ow: int) -> None:
        ln = 0.105 * S * es
        d.line([x - ln, y, x + ln, y], fill=p["eye"], width=max(2, ow))

    def _eyes(self, d: ImageDraw.ImageDraw, S: float, cx: float, cy: float,
              style: str, es: float, p: dict, ow: int, blink: bool) -> None:
        lx, rx = cx - EYE_DX * S, cx + EYE_DX * S
        ey = cy + EYE_DY * S
        if style == "wink":  # viewer-left eye open, right closed
            if blink:
                self._blink_line(d, lx, ey, S, es, p, ow)
            else:
                self._eye(d, lx, ey, S, "open", es, p, ow)
            self._blink_line(d, rx, ey, S, es, p, ow)
            return
        if blink:
            self._blink_line(d, lx, ey, S, es, p, ow)
            self._blink_line(d, rx, ey, S, es, p, ow)
            return
        self._eye(d, lx, ey, S, style, es, p, ow)
        self._eye(d, rx, ey, S, style, es, p, ow)

    # ── Brows ─────────────────────────────────────────────────────────
    def _brows(self, d: ImageDraw.ImageDraw, S: float, cx: float, cy: float,
               style: str, p: dict, ow: int) -> None:
        if style == "none":
            return
        w = max(2, ow + 1)
        bx, by = 0.05 * S, cy + BROW_DY * S
        if style == "raised":
            by -= 0.05 * S
        for side in (-1, 1):
            ex = cx + side * EYE_DX * S
            if style in ("flat", "raised"):
                d.line([ex - bx, by, ex + bx, by], fill=p["eye"], width=w)
            elif style == "angry":  # outer end high, inner end low
                d.line([ex + side * bx, by - 0.03 * S,
                        ex - side * bx, by + 0.03 * S], fill=p["eye"], width=w)
            elif style == "sad":  # inner end high, outer end low
                d.line([ex + side * bx, by + 0.03 * S,
                        ex - side * bx, by - 0.03 * S], fill=p["eye"], width=w)

    # ── Mouth ─────────────────────────────────────────────────────────
    def _mouth(self, d: ImageDraw.ImageDraw, S: float, cx: float, cy: float,
               style: str, ms: float, p: dict, ow: int) -> None:
        my = cy + MOUTH_DY * S
        w = max(2, ow)
        if style == "flat":
            hw = 0.07 * S * ms
            d.line([cx - hw, my, cx + hw, my], fill=p["eye"], width=w)
        elif style == "smile":
            rx, ry = 0.11 * S * ms, 0.07 * S * ms
            d.arc([cx - rx, my - ry, cx + rx, my + ry], 15, 165,
                  fill=p["eye"], width=w)
        elif style == "frown":
            rx, ry = 0.11 * S * ms, 0.07 * S * ms
            d.arc([cx - rx, my - ry, cx + rx, my + ry], 195, 345,
                  fill=p["eye"], width=w)
        elif style == "open":
            rx, ry = 0.075 * S * ms, 0.09 * S * ms
            d.ellipse([cx - rx, my - ry, cx + rx, my + ry],
                      fill=p["mouth"])
            d.ellipse([cx - rx * 0.45, my + ry * 0.15,
                       cx + rx * 0.45, my + ry * 0.9], fill=p["tongue"])
        elif style == "grin":
            rx, ry = 0.10 * S * ms, 0.065 * S * ms
            d.pieslice([cx - rx, my - ry, cx + rx, my + ry], 0, 180,
                       fill=p["mouth"], outline=p["outline"], width=ow)
            d.rectangle([cx - rx * 0.86, my - 0.004 * S,
                         cx + rx * 0.86, my + 0.024 * S * ms],
                        fill=p["eye_white"])
        elif style == "wavy":
            pts = []
            for i in range(9):
                t = i / 8
                x = cx + (t - 0.5) * 0.20 * S * ms
                y = my + 0.028 * S * math.sin(t * 3 * math.pi)
                pts.append((x, y))
            d.line(pts, fill=p["eye"], width=w, joint="curve")
        elif style == "cat":  # omega: two small arcs side by side
            rx, ry = 0.055 * S * ms, 0.045 * S * ms
            for side in (-1, 1):
                bx = cx + side * rx
                d.arc([bx - rx, my - ry, bx + rx, my + ry], 15, 165,
                      fill=p["eye"], width=w)

    # ── Extras ────────────────────────────────────────────────────────
    def _extras(self, d: ImageDraw.ImageDraw, S: float, cx: float, cy: float,
                style: str, es: float, p: dict, ow: int) -> None:
        if style == "blush":
            for side in (-1, 1):
                bx = cx + side * 0.21 * S
                by = cy + 0.07 * S
                rx, ry = 0.06 * S, 0.035 * S
                d.ellipse([bx - rx, by - ry, bx + rx, by + ry],
                          fill=p["accent"])
        elif style == "sweat":
            sx, sy = cx + 0.25 * S, cy - 0.30 * S
            r = 0.045 * S
            dark = palettes.darken(p["drop"], 0.62)
            # union-outline pass for the drop (circle + tip)
            d.ellipse([sx - r - ow, sy + 0.01 * S - r - ow,
                       sx + r + ow, sy + 0.01 * S + r + ow], fill=dark)
            d.polygon([(sx, sy - 0.10 * S - ow),
                       (sx - r - ow, sy + 0.01 * S + ow),
                       (sx + r + ow, sy + 0.01 * S + ow)], fill=dark)
            d.ellipse([sx - r, sy + 0.01 * S - r, sx + r, sy + 0.01 * S + r],
                      fill=p["drop"])
            d.polygon([(sx, sy - 0.10 * S), (sx - r, sy + 0.01 * S),
                       (sx + r, sy + 0.01 * S)], fill=p["drop"])
        elif style == "tears":
            ey = cy + EYE_DY * S
            for side in (-1, 1):
                tx = cx + side * EYE_DX * S
                ty = ey + 0.10 * S
                d.line([tx, ey + 0.05 * S, tx, ty], fill=p["drop"],
                       width=max(2, ow))
                r = 0.035 * S
                d.ellipse([tx - r, ty - r * 0.6, tx + r, ty + r * 1.4],
                          fill=p["drop"])
        elif style == "anger":
            ax, ay = cx + 0.23 * S, cy - 0.29 * S
            ln = 0.05 * S
            d.line([ax - ln, ay, ax + ln, ay], fill=p["anger"], width=ow)
            d.line([ax, ay - ln, ax, ay + ln], fill=p["anger"], width=ow)

    # ── Entry point ───────────────────────────────────────────────────
    def generate(self, seed, count, frame_px, params, base=0) -> list[FrameData]:
        mood = str(params.get("mood", "auto"))
        if mood != "auto" and mood not in MOODS:
            raise ValueError(
                f"invalid face.mood '{mood}' "
                f"(available: auto, {', '.join(MOODS)})"
            )
        resolved: dict[str, str] = {}
        for name, vocab in (("head", HEADS), ("eyes", EYES),
                            ("mouth", MOUTHS), ("brows", BROWS),
                            ("extras", EXTRAS)):
            val = str(params.get(name, "auto"))
            if val not in vocab:
                raise ValueError(
                    f"invalid face.{name} '{val}' "
                    f"(available: {', '.join(vocab)})"
                )
            resolved[name] = val

        vs = (seed * 1000 + base) % 2**31
        anat = _anatomy(vs)
        if resolved["head"] != "auto":
            anat["head"] = resolved["head"]
        if mood == "auto":
            mood = _pick(tuple(MOODS), vs, 12)
        parts = MOODS[mood]
        eyes = resolved["eyes"] if resolved["eyes"] != "auto" else parts["eyes"]
        mouth = resolved["mouth"] if resolved["mouth"] != "auto" else parts["mouth"]
        brows = resolved["brows"] if resolved["brows"] != "auto" else parts["brows"]
        extras = resolved["extras"] if resolved["extras"] != "auto" else parts["extras"]

        p = dict(self.DEFAULTS)
        p.update({k: tuple(v) for k, v in params.items()
                  if isinstance(v, list) and len(v) == 3})
        ow = palettes.outline_width(frame_px)

        blinkable = eyes in BLINKABLE
        blink_frame = (int(_rnd(vs, 90) * count)
                       if count >= 4 and blinkable else -1)

        S = float(frame_px)
        cx, cy = S * 0.5, S * 0.47
        es, ms = anat["eye_scale"], anat["mouth_scale"]
        out: list[FrameData] = []
        for i in range(count):
            blink = i == blink_frame
            img = Image.new("RGBA", (frame_px, frame_px), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            self._head(d, S, anat["head"], p, ow, cx, cy)
            self._brows(d, S, cx, cy, brows, p, ow)
            self._eyes(d, S, cx, cy, eyes, es, p, ow, blink)
            self._mouth(d, S, cx, cy, mouth, ms, p, ow)
            self._extras(d, S, cx, cy, extras, es, p, ow)
            out.append(FrameData(id="", image=img,
                                 meta={"anchor": _anchor_from_alpha(img)}))
        return out

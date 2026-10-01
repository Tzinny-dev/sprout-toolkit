"""``flora`` generator: trees and forest-floor plants.

Two kinds:

    tree    trunk + branches + canopy, three canopy shapes
            (``round`` blob cluster, ``columnar`` poplar, ``conifer``
            stacked tiers), two trunk styles (``straight``, ``gnarled`` =
            lean + kink) and four maturity stages (``sapling``, ``young``,
            ``mature``, ``old``) that scale the whole plant
    plant   low undergrowth picked by seed: ``fern``, ``sprout``,
            ``grass`` tuft, ``blossom`` (stem + petals)

Anatomy derives from ``seed * 1000 + base`` — the item's slot, never the
frame index — so every frame of an item is the *same* plant; frames differ
only by the optional ``sway`` phase (``sin(tau * i / count)`` displacing
the canopy / upper stem, pivot at the ground).

Canopies use a union-outline pass: every lobe is drawn first in the
outline color (radius + ow) and then in the fill color, so the silhouette
gets a clean ring without internal arcs. The outline follows the shared
rule (``palettes.outline_width``) and derives from each color role
(``darken(fill, .55)`` for foliage, ``darken(bark, .55)`` for wood) unless
an explicit ``outline`` param (or ``palette``) overrides both.

Tint-compatible: colors are plain ``fill``/``bark``/``accent`` roles.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from .. import palettes
from .base import FrameData, Generator
from .props import _anchor_from_alpha, _rnd

TAU = math.tau

KINDS = ("tree", "plant")
CANOPY = ("auto", "round", "columnar", "conifer")
TRUNK = ("auto", "straight", "gnarled")
AGES = ("auto", "sapling", "young", "mature", "old")
FORMS = ("auto", "fern", "sprout", "grass", "blossom")

# Maturity stages scale the seeded proportions of a tree. ``mature`` is all
# 1.0, so it reproduces the historical proportions exactly: an item that pins
# ``age: mature`` keeps the look it had before the param existed.
_AGE_MODS = {
    "sapling": {"trunk_h": 0.55, "trunk_w": 0.60, "canopy_r": 0.66,
                "branches": 0.50, "n_lobes": 0.85, "lean": 0.60,
                "kink": 0.60, "fruit_p": 0.0},
    "young":   {"trunk_h": 0.82, "trunk_w": 0.84, "canopy_r": 0.88,
                "branches": 0.75, "n_lobes": 0.95, "lean": 0.85,
                "kink": 0.85, "fruit_p": 0.0},
    "mature":  {"trunk_h": 1.00, "trunk_w": 1.00, "canopy_r": 1.00,
                "branches": 1.00, "n_lobes": 1.00, "lean": 1.00,
                "kink": 1.00, "fruit_p": 1.0},
    "old":     {"trunk_h": 0.90, "trunk_w": 1.40, "canopy_r": 1.14,
                "branches": 1.30, "n_lobes": 1.15, "lean": 1.45,
                "kink": 1.50, "fruit_p": 1.7},
}

SWAY_AMP = 0.028       # fraction of frame_px
CANOPY_MARGIN = 0.10   # keep the canopy tip >= 10% below the frame top

_PLANT_FORMS = ("fern", "sprout", "grass", "blossom")


def _pick(opts: tuple[str, ...], vs: int, salt: int) -> str:
    return opts[int(_rnd(vs, salt) * len(opts)) % len(opts)]


def _anatomy(vs: int, kind: str, age: str = "auto") -> dict:
    """One plant's fixed proportions (no frame index — stable per item).

    ``age`` is passed in (rather than overridden after the fact) because the
    stage scales the seeded values: forcing a stage has to re-apply its
    multipliers, not just relabel the tree.
    """
    if kind == "tree":
        if age == "auto":
            age = _pick(AGES[1:], vs, 13)
        m = _AGE_MODS[age]
        return {
            "age": age,
            "canopy": _pick(CANOPY[1:], vs, 11),
            "trunk": _pick(TRUNK[1:], vs, 12),
            "trunk_h": (0.26 + _rnd(vs, 31) * 0.14) * m["trunk_h"],
            "trunk_w": (0.075 + _rnd(vs, 32) * 0.040) * m["trunk_w"],
            "canopy_r": (0.22 + _rnd(vs, 33) * 0.08) * m["canopy_r"],
            "lean": (_rnd(vs, 34) - 0.5) * 0.16 * m["lean"],
            "kink": (_rnd(vs, 35) - 0.5) * 0.22 * m["kink"],
            "n_lobes": max(3, round((4 + int(_rnd(vs, 36) * 4)) * m["n_lobes"])),
            "branches": max(1, round((2 + int(_rnd(vs, 37) * 3)) * m["branches"])),
            # keep the original comparison direction so a mature tree keeps
            # the exact fruit it had before the param existed
            "fruit": _rnd(vs, 38) > 1.0 - min(1.0, 0.45 * m["fruit_p"]),
        }
    return {
        "form": _pick(_PLANT_FORMS, vs, 11),
        "size": 0.30 + _rnd(vs, 31) * 0.16,
        "lean": (_rnd(vs, 34) - 0.5) * 0.20,
    }

def _leaf(d: ImageDraw.ImageDraw, cx: float, cy: float, rx: float, ry: float,
          ang: float, fill: tuple, outline: tuple | None = None,
          width: int = 0) -> None:
    """Rotated ellipse (PIL has no rotated ellipse) as a 12-gon."""
    pts = []
    cos_a, sin_a = math.cos(ang), math.sin(ang)
    for i in range(12):
        t = TAU * i / 12
        x, y = math.cos(t) * rx, math.sin(t) * ry
        pts.append((cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a))
    if outline is not None:
        d.polygon(pts, fill=fill, outline=outline, width=width)
    else:
        d.polygon(pts, fill=fill)


class Flora(Generator):
    """Trees (trunk + canopy) and forest-floor plants."""

    id = "flora"

    PARAMS = frozenset({
        "kind", "canopy", "trunk", "age", "form", "sway",
        "fill", "outline", "bark", "accent",
    })

    KIND_DEFAULTS: dict[str, dict] = {
        "tree": {"fill": (94, 152, 78), "bark": (142, 102, 64),
                 "accent": (170, 210, 98)},
        "plant": {"fill": (86, 150, 84), "bark": (64, 104, 58),
                  "accent": (242, 168, 192)},
    }
    _CENTER = (246, 214, 110)  # blossom pistil (fixed warm)

    # ── Tree ──────────────────────────────────────────────────────────
    def _tree(self, d: ImageDraw.ImageDraw, S: float, anat: dict, p: dict,
              ow: int, dx: float) -> None:
        ground = S * 0.86
        cx = S * 0.5
        gnarled = anat["trunk"] == "gnarled"
        lean = (anat["lean"] if gnarled else 0.0) * S
        kink = (anat["kink"] if gnarled else 0.0) * S
        trunk_top = ground - anat["trunk_h"] * S
        tx = cx + lean                      # trunk top x
        mx = cx + kink                      # mid kink x
        my = ground - (ground - trunk_top) * 0.5
        hw0 = anat["trunk_w"] * S * 0.75    # base half width (root flare)
        hw_top = anat["trunk_w"] * S * 0.50

        def frac(y: float) -> float:
            # clamp at the canopy: everything above the trunk top shifts by dx
            return min(1.0, max(0.0, (ground - y) / max(1.0, ground - trunk_top)))

        def sway(y: float, x: float) -> float:
            return x + dx * frac(y)

        d.polygon([
            (cx - hw0, ground),
            (sway(my, mx) - (hw0 + hw_top) * 0.31, my),
            (sway(trunk_top, tx) - hw_top, trunk_top),
            (sway(trunk_top, tx) + hw_top, trunk_top),
            (sway(my, mx) + (hw0 + hw_top) * 0.31, my),
            (cx + hw0, ground),
        ], fill=p["bark"], outline=p["_out_bark"], width=ow)

        # tapered branch twigs just below the canopy (drawn before it, so
        # the canopy covers the part that reaches into the foliage)
        if anat["canopy"] != "conifer":
            cy_c, bottom_off, _ = self._canopy_geom(S, anat, trunk_top, ow)
            canopy_bottom = cy_c + bottom_off
            bw = max(2, int(round(S * 0.030)))
            for k in range(anat["branches"]):
                side = -1 if k % 2 == 0 else 1
                t = 0.78 + 0.08 * k
                ry = min(ground - (ground - trunk_top) * t,
                         canopy_bottom - 0.02 * S)
                rx = cx + (tx - cx) * t
                if ry > ground - 0.04 * S or ry < trunk_top + 0.03 * S:
                    continue
                ln = S * (0.09 + _rnd(anat["_vs"], 50 + k) * 0.05)
                a = math.radians(36.0 + _rnd(anat["_vs"], 60 + k) * 16.0)
                dxl, dyl = side * math.cos(a) * ln, -math.sin(a) * ln
                ux, uy = -dyl / ln, dxl / ln      # unit perpendicular
                tipx = sway(ry, rx) + dxl
                tipy = ry + dyl
                d.polygon([(sway(ry, rx) - ux * bw * 0.5, ry - uy * bw * 0.5),
                           (sway(ry, rx) + ux * bw * 0.5, ry + uy * bw * 0.5),
                           (tipx + ux * 0.7, tipy + uy * 0.7),
                           (tipx - ux * 0.7, tipy - uy * 0.7)],
                          fill=p["bark"], outline=p["_out_bark"],
                          width=max(1, ow // 2))

        self._canopy(d, S, anat, p, ow, dx, trunk_top, cx, lean)

    def _canopy_geom(self, S: float, anat: dict, trunk_top: float,
                     ow: int) -> tuple[float, float, float]:
        """(center y, distance to silhouette bottom, radius) for a canopy.

        ``ow`` pads the margin: the outline ring grows past the fill, so
        the design margin is measured from the *outlined* silhouette.
        """
        cr = anat["canopy_r"] * S
        m = CANOPY_MARGIN * S
        kind = anat["canopy"]
        extent = {"round": 1.10, "columnar": 1.05, "conifer": 1.10}[kind]
        cy = max(m + extent * cr, trunk_top - 0.85 * cr) + ow
        bottom = {"round": 1.05, "columnar": 1.05, "conifer": 1.10}[kind] * cr
        return cy, bottom, cr

    def _canopy(self, d: ImageDraw.ImageDraw, S: float, anat: dict, p: dict,
                ow: int, dx: float, trunk_top: float, cx: float,
                lean: float) -> None:
        kind = anat["canopy"]
        cy, _, cr = self._canopy_geom(S, anat, trunk_top, ow)
        ccx = cx + lean * 0.7 + dx
        lobes: list[tuple[float, float, float, float, float]] = []  # x,y,rx,ry

        if kind == "round":
            lobes.append((ccx, cy, cr * 0.60, cr * 0.60))
            n = anat["n_lobes"]
            for k in range(n):
                ang = TAU * k / n + (_rnd(anat["_vs"], 40 + k) - 0.5) * 0.8
                dist = cr * (0.30 + _rnd(anat["_vs"], 44 + k) * 0.14)
                r = cr * (0.48 + _rnd(anat["_vs"], 48 + k) * 0.18)
                lobes.append((ccx + math.cos(ang) * dist,
                              cy + math.sin(ang) * dist * 0.85, r, r))
        elif kind == "columnar":
            lobes.append((ccx, cy, cr * 0.45, cr * 1.05))
            lobes.append((ccx, cy - cr * 0.50, cr * 0.34, cr * 0.50))
        else:  # conifer: stacked tiers with visible seams (drawn individually)
            bottom = cy + 1.10 * cr
            for hw, base_d, apex_d in ((0.92, 0.00, 0.90), (0.64, 0.70, 1.55),
                                       (0.38, 1.40, 2.20)):
                y_base = bottom - base_d * cr
                d.polygon([(ccx - hw * cr, y_base), (ccx + hw * cr, y_base),
                           (ccx, bottom - apex_d * cr)],
                          fill=p["fill"], outline=p["_out_fill"], width=ow)
            return

        # union-outline pass: outline ring around the merged silhouette
        for x, y, rx, ry in lobes:
            d.ellipse([x - rx - ow, y - ry - ow, x + rx + ow, y + ry + ow],
                      fill=p["_out_fill"])
        for x, y, rx, ry in lobes:
            d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=p["fill"])

        if kind == "round":
            d.ellipse([ccx - cr * 0.32 - cr * 0.28, cy - cr * 0.50 - cr * 0.24,
                       ccx - cr * 0.32 + cr * 0.28, cy - cr * 0.50 + cr * 0.24],
                      fill=p["accent"])
        else:
            d.ellipse([ccx - cr * 0.46, cy - cr * 0.95, ccx - cr * 0.22,
                       cy + cr * 0.30], fill=p["accent"])

        if anat["fruit"] and kind == "round":
            n = 3 + int(_rnd(anat["_vs"], 54) * 3)
            fr = max(1.4, S * 0.018)
            ang0 = _rnd(anat["_vs"], 55) * TAU
            for k in range(n):
                ang = ang0 + k * 2.3999638          # golden angle: no clumps
                dist = cr * (0.32 + _rnd(anat["_vs"], 56 + k) * 0.16)
                fx = ccx + math.cos(ang) * dist
                fy = cy + math.sin(ang) * dist
                d.ellipse([fx - fr, fy - fr, fx + fr, fy + fr],
                          fill=p["accent"])

    # ── Plant (undergrowth) ───────────────────────────────────────────
    def _plant(self, d: ImageDraw.ImageDraw, S: float, anat: dict, p: dict,
               ow: int, dx: float) -> None:
        ground = S * 0.86
        cx = S * 0.5
        h = anat["size"] * S
        lean = anat["lean"] * S
        form = anat["form"]
        vs = anat["_vs"]

        def sway(y: float, x: float) -> float:
            return x + dx * max(0.0, (ground - y) / max(1.0, h))

        if form == "grass":
            n = 6 + int(_rnd(vs, 32) * 4)   # 6-9 blades: gaps stay visible
            for k in range(n):
                back = k < max(2, n // 3)
                bx = cx + (_rnd(vs, 40 + k) - 0.5) * S * 0.44
                dirn = (_rnd(vs, 44 + k) - 0.5) * 2.0
                bh = h * (0.45 + _rnd(vs, 48 + k) * 0.75)
                if back:
                    bh *= 1.35             # tall back row = depth, no slab
                w0 = max(1.0, S * 0.014 * (0.7 + _rnd(vs, 52 + k) * 0.6))
                col = palettes.darken(p["fill"], 0.72) if back else p["fill"]
                ts = (0.0, 0.3, 0.6, 0.85, 1.0)
                left, right = [], []
                for t in ts:
                    y = ground - bh * t
                    x = bx + dirn * S * 0.16 * (t ** 1.6)
                    w = w0 * (1.0 - t) ** 0.85
                    left.append((sway(y, x) - w, y))
                    right.append((sway(y, x) + w, y))
                d.polygon(left + list(reversed(right)), fill=col)
            return

        if form == "fern":
            n = 5 + int(_rnd(vs, 32) * 3)   # 5-7 fronds
            w = max(1, int(round(S * 0.020)))
            leaf_r = S * 0.024
            for k in range(n):
                back = k < n // 2
                th = (-0.55 + 1.1 * (k + 0.5) / n) \
                    + (_rnd(vs, 40 + k) - 0.5) * 0.12
                ln = h * (0.90 + _rnd(vs, 44 + k) * 0.35)
                col = palettes.darken(p["fill"], 0.72) if back else p["fill"]
                # quadratic bezier: rise mostly upright, gentle arch at tip
                x0, y0 = cx, ground
                x1, y1 = cx + math.sin(th) * ln * 0.30, ground - ln * 1.0
                x2, y2 = cx + math.sin(th) * ln * 0.60, ground - ln * 0.65

                def bez(t: float, _a=(x0, y0), _b=(x1, y1),
                        _c=(x2, y2)) -> tuple[float, float]:
                    a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t ** 2
                    return a * _a[0] + b * _b[0] + c * _c[0], \
                        a * _a[1] + b * _b[1] + c * _c[1]

                pts = []
                for i in range(7):
                    x, y = bez(i / 6)
                    pts.append((sway(y, x), y))
                d.line(pts, fill=col, width=w, joint="curve")
                # pinnae: small leaflets along both sides of the rachis
                for i in range(1, 7):
                    t = i / 7
                    x, y = bez(t)
                    xa, ya = bez(min(1.0, t + 0.08))
                    xb, yb = bez(max(0.0, t - 0.08))
                    tl = math.hypot(xa - xb, ya - yb) or 1.0
                    nx, ny = -(ya - yb) / tl, (xa - xb) / tl
                    ll = leaf_r * (1.0 - 0.75 * t) * \
                        (0.8 + 0.4 * _rnd(vs, 60 + k * 8 + i))
                    for sidep in (-1, 1):
                        lx = sway(y, x) + nx * ll * 0.7 * sidep
                        ly = y + ny * ll * 0.7 * sidep
                        _leaf(d, lx, ly, ll, ll * 0.5,
                              math.atan2(ny * sidep, nx * sidep), col, None, 0)
            return

        # stem-based forms (sprout / blossom)
        stem_w = max(2, int(round(S * 0.035)))
        p0, p1, p2 = (cx, ground), (cx + lean * 0.4, ground - h * 0.55), \
            (cx + lean, ground - h)
        stem_pts = []
        for i in range(5):
            t = i / 4
            a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t ** 2
            x = a * p0[0] + b * p1[0] + c * p2[0]
            y = a * p0[1] + b * p1[1] + c * p2[1]
            stem_pts.append((x, y))
        d.line([(sway(y, x), y) for x, y in stem_pts], fill=p["bark"],
               width=stem_w, joint="curve")

        n_leaves = 2 + int(_rnd(vs, 42) * 3)
        for k in range(n_leaves):
            if n_leaves > 1:
                t = 0.50 + 0.42 * k / (n_leaves - 1)
            else:
                t = 0.7
            side = -1 if k % 2 == 0 else 1
            ly = ground - h * t
            lx = cx + lean * t * t
            ln = h * (0.34 + _rnd(vs, 46 + k) * 0.22)
            ang = -0.45 if side > 0 else math.pi + 0.45
            cxx = sway(ly, lx) + math.cos(ang) * ln * 0.45
            cyy = ly + math.sin(ang) * ln * 0.45
            _leaf(d, cxx, cyy, ln * 0.5, ln * 0.3, ang,
                  p["fill"], p["_out_fill"], max(1, ow // 2))

        if form == "blossom":
            pr = h * (0.20 + _rnd(vs, 43) * 0.10)
            hx, hy = sway(p2[1], p2[0]), p2[1]
            n_p = 5 + int(_rnd(vs, 44) * 3)
            for k in range(n_p):
                ang = TAU * k / n_p
                px = hx + math.cos(ang) * pr * 0.55
                py = hy + math.sin(ang) * pr * 0.55
                _leaf(d, px, py, pr * 0.55, pr * 0.32, ang,
                      p["accent"], p["_out_accent"], max(1, ow // 2))
            cr = pr * 0.45
            d.ellipse([hx - cr, hy - cr, hx + cr, hy + cr],
                      fill=self._CENTER)

    # ── Entry point ───────────────────────────────────────────────────
    def generate(self, seed, count, frame_px, params, base=0) -> list[FrameData]:
        kind = str(params.get("kind", "tree"))
        if kind not in KINDS:
            raise ValueError(
                f"invalid flora.kind '{kind}' (available: {', '.join(KINDS)})"
            )
        for name, vocab in (("canopy", CANOPY), ("trunk", TRUNK), ("age", AGES),
                             ("form", FORMS)):
            val = str(params.get(name, "auto"))
            if val not in vocab:
                raise ValueError(
                    f"invalid flora.{name} '{val}' "
                    f"(available: {', '.join(vocab)})"
                )
        sway = params.get("sway", False)
        if not isinstance(sway, bool):
            raise ValueError(
                f"invalid flora.sway {sway!r} (expected a JSON boolean)"
            )

        vs = (seed * 1000 + base) % 2**31
        # the stage has to reach _anatomy (it scales the proportions), while
        # canopy/trunk/form are plain replacements
        anat = _anatomy(vs, kind, str(params.get("age", "auto")))
        anat["_vs"] = vs
        for name in ("canopy", "trunk", "form"):
            val = str(params.get(name, "auto"))
            if val != "auto":
                anat[name] = val

        p: dict = dict(self.KIND_DEFAULTS[kind])
        p.update({k: tuple(v) for k, v in params.items()
                  if isinstance(v, list) and len(v) == 3})
        explicit_outline = "outline" in p
        p["_out_fill"] = p["outline"] if explicit_outline else \
            palettes.outline_color(p["fill"])
        p["_out_bark"] = p["outline"] if explicit_outline else \
            palettes.outline_color(p["bark"])
        p["_out_accent"] = p["outline"] if explicit_outline else \
            palettes.outline_color(p["accent"])
        ow = palettes.outline_width(frame_px)

        renderer = self._tree if kind == "tree" else self._plant
        amp = SWAY_AMP * frame_px
        out: list[FrameData] = []
        for i in range(count):
            dx = math.sin(TAU * i / count) * amp if sway else 0.0
            img = Image.new("RGBA", (frame_px, frame_px), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            renderer(d, float(frame_px), anat, p, ow, dx)
            out.append(FrameData(id="", image=img,
                                 meta={"anchor": _anchor_from_alpha(img)}))
        return out

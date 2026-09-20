"""``particles`` generator: animated particle bursts with easing.

Each frame is a snapshot of the same burst: particles expand radially
from the center with an *ease-out cubic*, shrinking and fading out as
progress advances. The seed fixes angle/speed/life/size for each particle,
so the whole animation is deterministic and reproducible.

Spec parameters (item.params):
    kind      : "spark" | "smoke" | "dust" | "bubble"  (default "spark")
    particles : number of particles (default 12, minimum 2)
    core      : [r, g, b]  core color (optional override)
    trail     : [r, g, b]  trail color (optional override)
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from .base import FrameData, Generator


# ── Deterministic hash (identical to the one in terrain/props) ──────────
def _cell(i: int, j: int, seed: int) -> float:
    h = (i * 374761393 + j * 668265263 + seed * 974711377) % 2**32
    return ((h >> 8) % 2**24) / 2**24


def _rnd(seed: int, i: int) -> float:
    """Ubiquitous [0, 1) value for per-particle variation."""
    return _cell(i, 0, seed)


def ease_out_cubic(t: float) -> float:
    """Deceleration easing: 1 - (1-t)^3, with t clamped to [0, 1]."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


class Particles(Generator):
    """Animated bursts: sparks, smoke, dust and bubbles."""

    id = "particles"

    KIND_DEFAULTS: dict[str, dict] = {
        "spark":  {"core": (255, 235, 130), "trail": (255, 130, 30)},
        "smoke":  {"core": (205, 205, 210), "trail": (110, 110, 118)},
        "dust":   {"core": (200, 180, 150), "trail": (135, 115, 90)},
        "bubble": {"core": (225, 245, 255), "trail": (120, 185, 235)},
    }

    # Per kind: (relative reach, shrink amount, relative gravity)
    MOTION: dict[str, tuple[float, float, float]] = {
        "spark":  (0.46, 0.72, -0.10),  # rises and fades out
        "smoke":  (0.34, 0.30,  0.20),  # floats upward
        "dust":   (0.40, 0.55,  0.06),  # settles down
        "bubble": (0.30, 0.15, -0.24),  # ascends
    }

    def generate(
        self,
        seed: int,
        count: int,
        frame_px: int,
        params: dict,
        base: int = 0,
    ) -> list[FrameData]:
        kind = params.get("kind", "spark")
        if kind not in self.KIND_DEFAULTS:
            raise ValueError(
                f"invalid particles.kind '{kind}' "
                f"(available: {', '.join(sorted(self.KIND_DEFAULTS))})"
            )
        palette: dict = dict(self.KIND_DEFAULTS[kind])
        for key in ("core", "trail"):
            v = params.get(key)
            if isinstance(v, list) and len(v) == 3:
                palette[key] = tuple(int(c) for c in v)

        n_part = max(2, int(params.get("particles", 12)))
        n_frames = max(2, int(count))
        reach, shrink, gravity = self.MOTION[kind]
        vs = (seed * 1000 + base) % 2**31

        core = palette["core"]
        trail = palette["trail"]

        out: list[FrameData] = []
        for f in range(n_frames):
            t = (f + 0.5) / n_frames
            frame = Image.new("RGBA", (frame_px, frame_px), (0, 0, 0, 0))
            cx = cy = frame_px / 2
            max_r = frame_px * reach

            for k in range(n_part):
                # Step-1 indices: the `_cell` hash advances ~0.087 per index
                # unit, so a step of 1 spreads the values well; a step of 6
                # would cluster them into ~2 values (opposing arcs).
                ang = math.tau * _rnd(vs, k)
                speed = 0.55 + 0.45 * _rnd(vs, 100 + k)
                life = 0.55 + 0.45 * _rnd(vs, 200 + k)
                r0 = (0.07 + 0.07 * _rnd(vs, 300 + k)) * frame_px
                start = (0.10 + 0.10 * _rnd(vs, 400 + k)) * max_r
                jitter = (_rnd(vs, 500 + k) - 0.5) * 0.3

                p = t / life
                if p >= 1.0:
                    continue  # particle has already died out
                e = ease_out_cubic(p)
                dist = start + e * speed * max_r
                px = cx + math.cos(ang) * dist
                py = cy + math.sin(ang) * dist + gravity * frame_px * (e + jitter * p)
                rad = r0 * (1.0 - shrink * p)
                alpha = int(255 * (1.0 - p) ** 0.8)
                if rad < 0.5 or alpha <= 0:
                    continue

                # Trail (behind, bigger and dimmer). Composited on its own
                # layer: PIL overwrites pixels when drawing onto RGBA, so
                # without alpha_composite the particles would "cut into" each
                # other.
                tr = rad * 1.4
                tl = Image.new("RGBA", (frame_px, frame_px), (0, 0, 0, 0))
                ImageDraw.Draw(tl).ellipse(
                    [px - tr, py - tr, px + tr, py + tr],
                    fill=trail + (max(1, int(alpha * 0.30)),))
                frame = Image.alpha_composite(frame, tl)

                # Core
                cl = Image.new("RGBA", (frame_px, frame_px), (0, 0, 0, 0))
                ImageDraw.Draw(cl).ellipse(
                    [px - rad, py - rad, px + rad, py + rad],
                    fill=core + (alpha,))
                frame = Image.alpha_composite(frame, cl)

            out.append(FrameData(id="", image=frame))
        return out
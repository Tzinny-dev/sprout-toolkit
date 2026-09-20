"""`terrain` generator: deterministic seamless noise tiles.

Value-noise FBM on a toroidal lattice (period = frame_px), mapped onto a
palette. Each tile uses a derived seed (``seed`` mixed with its index) to
vary the pattern without breaking determinism.

Autotile mode (``params.autotile == 16 | 47``): instead of a single fill
tile, produces the full sheet of silhouette variants. The shape is composed
by quadrants (2x2) according to the canonical mask: a side with no neighbor
is inset by ``bevel``, and a concave corner (both sides present, diagonal
absent) gets bitten. All variants share the same noise field so they tile
seamlessly when painting the map.
"""
from __future__ import annotations

import math

from PIL import Image

from .. import autotile
from .base import FrameData, Generator

PALETTE = [
    (0.16, 0.27, 0.16),
    (0.22, 0.34, 0.19),
    (0.33, 0.44, 0.22),
    (0.47, 0.52, 0.26),
    (0.66, 0.62, 0.31),
    (0.82, 0.72, 0.38),
    (0.90, 0.79, 0.46),
]


def cell(i: int, j: int, seed: int) -> float:
    h = (i * 374761393 + j * 668265263 + seed * 974711377) % 2**32
    return ((h >> 8) % 2**24) / 2**24


def smth(x: float) -> float:
    return x * x * (3 - 2 * x)


def seamless_noise(w: int, h: int, cells: int, octaves: int, seed: int) -> list[list[float]]:
    grid: list[list[float]] = [[0.0] * w for _ in range(h)]
    for bo in range(octaves):
        amp = 0.5**bo
        c = cells << bo
        for y in range(h):
            ky = y * c / h
            j0, fy0 = math.floor(ky), ky - math.floor(ky)
            fy = smth(fy0)
            for x in range(w):
                kx = x * c / w
                i0, fx0 = math.floor(kx), kx - math.floor(kx)
                fx = smth(fx0)
                a = cell(i0 % c, j0 % c, seed)
                b = cell((i0 + 1) % c, j0 % c, seed)
                cc = cell(i0 % c, (j0 + 1) % c, seed)
                d = cell((i0 + 1) % c, (j0 + 1) % c, seed)
                top = a + (b - a) * fx
                bot = cc + (d - cc) * fx
                grid[y][x] += (top + (bot - top) * fy) * amp
    return grid


def _blend(base: tuple[int, int, int], noise: float) -> tuple[int, int, int]:
    n = max(0.0, min(1.0, noise))
    seg = n * (len(PALETTE) - 1)
    i = min(int(seg), len(PALETTE) - 2)
    t = seg - i
    c0, c1 = PALETTE[i], PALETTE[i + 1]
    return tuple(int((c0[k] + (c1[k] - c0[k]) * t) * 255) for k in range(3))


def _tile_land(mask: int, size: int, u: float, v: float, bevel: float) -> bool:
    """Is the point (u,v) ∈ [0,1)² of the tile land, for ``mask``?"""
    if size == 16:
        # Match Sides: rectangle inset by ``bevel`` on each side with no
        # neighbor; the diagonal is ignored (straight interior corners).
        return (
            (u >= bevel or bool(mask & autotile.W))
            and (u <= 1.0 - bevel or bool(mask & autotile.E))
            and (v >= bevel or bool(mask & autotile.N))
            and (v <= 1.0 - bevel or bool(mask & autotile.S))
        )

    left, top = u < 0.5, v < 0.5
    if left and top:
        hb, vb, dg = mask & autotile.N, mask & autotile.W, mask & autotile.NW
        lx, ly = u, v
    elif (not left) and top:
        hb, vb, dg = mask & autotile.N, mask & autotile.E, mask & autotile.NE
        lx, ly = 1.0 - u, v
    elif left and (not top):
        hb, vb, dg = mask & autotile.S, mask & autotile.W, mask & autotile.SW
        lx, ly = u, 1.0 - v
    else:
        hb, vb, dg = mask & autotile.S, mask & autotile.E, mask & autotile.SE
        lx, ly = 1.0 - u, 1.0 - v

    if lx < (0.0 if vb else bevel) or ly < (0.0 if hb else bevel):
        return False
    if hb and vb and not dg and lx < bevel and ly < bevel:
        return False
    return True


class Terrain(Generator):
    id = "terrain"

    def generate(
        self,
        seed: int,
        count: int,
        frame_px: int,
        params: dict,
        base: int = 0,
    ) -> list[FrameData]:
        auto = params.get("autotile")
        if auto:
            return self._generate_autotile(seed, int(auto), count, frame_px, params)

        contrast = float(params.get("contrast", 0.85))
        lift = float(params.get("lift", 0.075))
        cells = int(params.get("cells", 3))
        octaves = int(params.get("octaves", 4))
        out: list[FrameData] = []
        for i in range(count):
            tile_seed = (seed * 1000 + base + i) % 2**31
            n = seamless_noise(frame_px, frame_px, cells, octaves, tile_seed)
            img = Image.new("RGB", (frame_px, frame_px))
            px = img.load()
            for y in range(frame_px):
                for x in range(frame_px):
                    px[x, y] = _blend((0, 0, 0), n[y][x] * contrast + lift)
            out.append(FrameData(id="", image=img))
        return out

    def _generate_autotile(
        self,
        seed: int,
        size: int,
        count: int,
        frame_px: int,
        params: dict,
    ) -> list[FrameData]:
        contrast = float(params.get("contrast", 0.85))
        lift = float(params.get("lift", 0.075))
        cells = int(params.get("cells", 3))
        octaves = int(params.get("octaves", 4))
        bevel = float(params.get("bevel", 0.16))

        variant = autotile.masks(size)
        if count != len(variant):
            raise ValueError(
                f"autotile {size} requires {len(variant)} frames, spec asked for {count}"
            )

        n = seamless_noise(frame_px, frame_px, cells, octaves, seed % 2**31)
        base_img = Image.new("RGB", (frame_px, frame_px))
        bpx = base_img.load()
        for y in range(frame_px):
            for x in range(frame_px):
                bpx[x, y] = _blend((0, 0, 0), n[y][x] * contrast + lift)

        out: list[FrameData] = []
        for mask in variant:
            img = Image.new("RGBA", (frame_px, frame_px), (0, 0, 0, 0))
            alpha = Image.new("L", (frame_px, frame_px), 0)
            apx = alpha.load()
            for y in range(frame_px):
                v = (y + 0.5) / frame_px
                for x in range(frame_px):
                    u = (x + 0.5) / frame_px
                    if _tile_land(mask, size, u, v, bevel):
                        apx[x, y] = 255
            img.paste(base_img, (0, 0), alpha)
            out.append(FrameData(id="", image=img, meta={"autotile_mask": mask}))
        return out
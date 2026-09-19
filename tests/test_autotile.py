"""Tests del builder autotile 16/47."""
from __future__ import annotations

import json
import random
import zlib
from pathlib import Path

import pytest
from PIL import Image

from imgi import autotile
from imgi.cli import _generate
from imgi.generators.terrain import Terrain, _tile_land as _land
from imgi.spec import SpecError, load_spec

SPEC = Path(__file__).resolve().parents[1] / "specs" / "autotile.json"


def _crc(p: Path) -> int:
    return zlib.crc32(p.read_bytes()) & 0xFFFFFFFF


def test_masks_counts_and_order() -> None:
    m47 = autotile.masks(47)
    m16 = autotile.masks(16)
    assert len(m47) == 47
    assert len(m16) == 16
    assert m47 == sorted(m47)
    assert m47[:5] == [0, 1, 4, 5, 7]
    assert m47[-1] == 255
    assert all(autotile.canonical(m, 47) == m for m in m47)
    assert all(autotile.canonical(m, 16) == m for m in m16)


def test_canonical_rule() -> None:
    n, ne, e, se, s, sw, w, nw = (autotile.N, autotile.NE, autotile.E, autotile.SE,
                                  autotile.S, autotile.SW, autotile.W, autotile.NW)
    # diagonal aislada no cuenta
    assert autotile.canonical_47(ne) == 0
    assert autotile.canonical_47(nw | ne | se | sw) == 0
    # diagonal cuenta solo con ambos cardinales
    assert autotile.canonical_47(n | e | ne) == n | e | ne
    assert autotile.canonical_47(n | ne) == n
    # 16 colapsa a los 4 lados
    assert autotile.canonical_16(n | ne | e | se | s | sw | w | nw) == n | e | s | w


def test_spec_rejects_bad_autotile(tmp_path: Path) -> None:
    def write(spec: dict) -> Path:
        p = tmp_path / "s.json"
        p.write_text(json.dumps(spec))
        return p

    base = {"name": "x", "seed": 1, "layout": {"cols": 8},
            "items": [{"id": "t", "generator": "terrain", "frames": 47,
                       "autotile": "99"}]}
    with pytest.raises(SpecError, match="autotile"):
        load_spec(write(base))

    base["items"][0]["autotile"] = "47"
    base["items"][0]["frames"] = 16
    with pytest.raises(SpecError, match="frames=47"):
        load_spec(write(base))

    base["items"][0]["autotile"] = "47"
    base["items"][0]["frames"] = 47
    base["items"][0]["generator"] = "blob_walk"
    with pytest.raises(SpecError, match="terrain"):
        load_spec(write(base))


def test_manifest_autotile_block(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    m = json.loads((out / "manifest.json").read_text())
    auto = m["autotile"]
    assert auto["bitmask"] == autotile.BITMASK
    entry = auto["items"]["terrain"]
    assert entry["size"] == 47
    assert len(entry["mask"]) == 47
    assert entry["mask"]["255"] == "terrain_46"
    assert entry["mask"]["0"] == "terrain_00"
    assert set(entry["mask"].values()) == {f"terrain_{i:02d}" for i in range(47)}


def test_autotile_atlas_deterministic(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    _generate(SPEC, a, None, False)
    _generate(SPEC, b, None, False)
    assert _crc(a / "atlas.png") == _crc(b / "atlas.png")
    assert (a / "manifest.json").read_bytes() == (b / "manifest.json").read_bytes()


def test_index_ts_exposes_autotile_helpers(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    src = (out / "index.ts").read_text()
    assert "AUTOTILE_BITS" in src
    assert "export function canonicalMask" in src
    assert "export function autotileFrame" in src


def _tile_edge_continuity(size: int = 47, frame_px: int = 24,
                          trials: int = 40) -> int:
    """Cuenta desajustes de tierra en bordes compartidos por tiles de tierra."""
    n, e, s, w = autotile.N, autotile.E, autotile.S, autotile.W
    eps = 0.5 / frame_px
    bevel = 0.16

    def mask_at(g: dict, r: int, c: int) -> int:
        def b(dr: int, dc: int) -> int:
            return 1 if g.get((r + dr, c + dc), False) else 0
        return (b(-1, 0) * autotile.N | b(-1, 1) * autotile.NE | b(0, 1) * autotile.E
                | b(1, 1) * autotile.SE | b(1, 0) * autotile.S
                | b(1, -1) * autotile.SW | b(0, -1) * autotile.W
                | b(-1, -1) * autotile.NW)

    from imgi.generators.terrain import _tile_land
    random.seed(1)
    bad = 0
    for _ in range(trials):
        g = {(r, c): random.random() < 0.5 for r in range(6) for c in range(6)}
        for r in range(6):
            for c in range(6):
                if not g[(r, c)]:
                    continue
                m = mask_at(g, r, c)
                if c + 1 < 6 and g[(r, c + 1)]:
                    mn = mask_at(g, r, c + 1)
                    for y in range(frame_px):
                        v = (y + 0.5) / frame_px
                        if _tile_land(m, size, 1 - eps, v, bevel) != \
                           _tile_land(mn, size, eps, v, bevel):
                            bad += 1
                if r + 1 < 6 and g[(r + 1, c)]:
                    mb = mask_at(g, r + 1, c)
                    for x in range(frame_px):
                        u = (x + 0.5) / frame_px
                        if _tile_land(m, size, u, 1 - eps, bevel) != \
                           _tile_land(mb, size, u, eps, bevel):
                            bad += 1
    return bad


def test_geometry_47_is_seamless() -> None:
    assert _tile_edge_continuity(47) == 0


def test_match_sides_is_inset_rectangle() -> None:
    """En 16 la silueta es el rectángulo retraído ``bevel`` de cada lado sin vecino."""
    n, e, s, w = autotile.N, autotile.E, autotile.S, autotile.W
    bevel = 0.25
    inside = (0.5, 0.5)
    assert _land(n | e | s | w, 16, *inside, bevel)  # todo conectado -> lleno
    # con W ausente, un punto pegado al borde oeste queda fuera; el resto dentro
    assert not _land(n | e | s, 16, 0.1, 0.5, bevel)
    assert _land(n | e | s, 16, 0.4, 0.5, bevel)
    # las diagonales no alteran la silueta 16
    assert _land(n | e | s, 16, 0.4, 0.5, bevel) == _land(n | e | s | autotile.NE, 16, 0.4, 0.5, bevel)

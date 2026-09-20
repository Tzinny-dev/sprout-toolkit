"""Tests for the `particles` generator (animated bursts)."""
from __future__ import annotations

import json
import zlib
from pathlib import Path

import pytest

from sprout.cli import _generate
from sprout.generators import GENERATORS
from sprout.generators.particles import Particles, ease_out_cubic

SPEC = Path(__file__).resolve().parents[1] / "specs" / "particles.json"

ALL_KINDS = ("spark", "smoke", "dust", "bubble")


def _crc(p: Path) -> int:
    return zlib.crc32(p.read_bytes()) & 0xFFFFFFFF


def _alpha_px(img) -> int:
    """Pixels with alpha > 0 (no numpy: histogram of the A channel)."""
    return sum(img.getchannel("A").histogram()[1:])


# ── Easing ──────────────────────────────────────────────────────────────
def test_ease_out_cubic_endpoints_and_monotonic() -> None:
    assert ease_out_cubic(0.0) == 0.0
    assert ease_out_cubic(1.0) == 1.0
    # saturates out of range
    assert ease_out_cubic(-5.0) == 0.0
    assert ease_out_cubic(9.0) == 1.0
    vals = [ease_out_cubic(i / 20) for i in range(21)]
    assert vals == sorted(vals), "must be monotonically increasing"
    # decelerates: the first stretch advances more than the last
    assert vals[5] - vals[0] > vals[20] - vals[15]


# ── Plug-in contract ─────────────────────────────────────────────────────
def test_registered() -> None:
    assert Particles.id == "particles"
    assert GENERATORS["particles"] is Particles


def test_all_kinds_animate_without_empty_frames() -> None:
    gen = Particles()
    for kind in ALL_KINDS:
        frames = gen.generate(seed=7, count=8, frame_px=64,
                              params={"kind": kind, "particles": 12})
        assert len(frames) == 8
        cov = [_alpha_px(f.image) for f in frames]
        assert all(c > 0 for c in cov), f"kind '{kind}' has empty frames: {cov}"
        assert max(cov) > 100, f"kind '{kind}' renders too little: {cov}"


def test_burst_expands_over_frames() -> None:
    """The burst's bbox must grow between the initial frame and the peak."""
    frames = Particles().generate(7, 8, 64, {"kind": "spark", "particles": 14})

    def bbox_w(img) -> float:
        bb = img.getchannel("A").getbbox()
        return 0.0 if bb is None else bb[2] - bb[0]

    assert bbox_w(frames[3].image) > bbox_w(frames[0].image)


def test_invalid_kind_raises() -> None:
    with pytest.raises(ValueError, match="kind"):
        Particles().generate(1, 4, 64, {"kind": "lava"})


def test_minimum_frames_saturated_to_two() -> None:
    """Saturates to >=2 frames."""
    assert len(Particles().generate(1, 1, 64, {"kind": "spark"})) == 2


def test_particle_count_floor_is_two() -> None:
    """`particles: 0` -> minimum 2; the start of the burst always has content.

    Note: with few particles the final frames may end up empty (the
    burst dies out) — this is expected behavior for a one-shot effect.
    """
    frames = Particles().generate(1, 4, 64, {"kind": "spark", "particles": 0})
    assert len(frames) == 4
    assert _alpha_px(frames[0].image) > 0


# ── Determinism ───────────────────────────────────────────────────────────
def test_same_seed_is_byte_identical() -> None:
    a = Particles().generate(42, 6, 64, {"kind": "smoke"})
    b = Particles().generate(42, 6, 64, {"kind": "smoke"})
    assert [f.image.tobytes() for f in a] == [f.image.tobytes() for f in b]


def test_seed_changes_output() -> None:
    a = Particles().generate(1, 6, 64, {"kind": "spark"})
    b = Particles().generate(2, 6, 64, {"kind": "spark"})
    assert [f.image.tobytes() for f in a] != [f.image.tobytes() for f in b]


def test_base_offset_changes_burst() -> None:
    a = Particles().generate(5, 4, 64, {"kind": "dust"}, base=0)
    b = Particles().generate(5, 4, 64, {"kind": "dust"}, base=100)
    assert a[0].image.tobytes() != b[0].image.tobytes()


# ── Parameters ────────────────────────────────────────────────────────────
def test_particle_count_scales_coverage() -> None:
    few = Particles().generate(3, 4, 64, {"kind": "spark", "particles": 4})
    many = Particles().generate(3, 4, 64, {"kind": "spark", "particles": 40})
    assert max(_alpha_px(f.image) for f in many) > \
        max(_alpha_px(f.image) for f in few)


def test_color_override_applied() -> None:
    frames = Particles().generate(
        1, 4, 64, {"kind": "spark", "core": [10, 20, 30], "trail": [1, 2, 3]}
    )
    colors = {px[:3] for f in frames for px in f.image.getdata() if px[3] > 0}
    assert (10, 20, 30) in colors


def test_size_scales_with_frame_px() -> None:
    for size in (32, 64, 128):
        frames = Particles().generate(3, 4, size, {"kind": "bubble"})
        assert all(f.image.size == (size, size) for f in frames)


# ── Full pipeline (spec -> atlas + manifest + index.ts) ──────────────────
def test_spec_generates_all_outputs(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    assert (out / "atlas.png").is_file()
    assert (out / "manifest.json").is_file()
    assert (out / "index.ts").is_file()


def test_spec_deterministic(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    _generate(SPEC, a, None, False)
    _generate(SPEC, b, None, False)
    assert _crc(a / "atlas.png") == _crc(b / "atlas.png")
    assert (a / "manifest.json").read_bytes() == (b / "manifest.json").read_bytes()


def test_manifest_frames_and_animation(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    m = json.loads((out / "manifest.json").read_text())
    # 4 kinds x 8 frames
    assert len(m["frames"]) == 32
    ids = {f["id"] for f in m["frames"]}
    assert "spark_00" in ids and "bubble_07" in ids
    # one-shot animation declared in the spec
    assert m["anim"]["burst_spark"]["fps"] == 16
    assert m["anim"]["burst_spark"]["loop"] is False
    assert m["anim"]["burst_spark"]["frames"] == [f"spark_{i:02d}" for i in range(8)]
    assert m["files"]["atlasW"] == 512 and m["files"]["atlasH"] == 256
    assert m["meta"]["generator"]["name"] == "sprout"

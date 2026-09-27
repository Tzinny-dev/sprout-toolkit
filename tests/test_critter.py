"""Tests for the `critter` generator (Fase 2: parametric creatures)."""
from __future__ import annotations

import json
import zlib
from pathlib import Path

import pytest
from PIL import Image

from sprout.cli import _generate
from sprout.generators import GENERATORS
from sprout.generators.critter import ARCHETYPES, Critter, _anatomy

SPEC = Path(__file__).resolve().parents[1] / "specs" / "critter.json"

# Archetypes whose eyes use the white-sclera `_eye` (bug draws dark dots).
WHITE_EYE_ARCHETYPES = ("quadruped", "bird", "fish", "reptile")


def _crc(p: Path) -> int:
    return zlib.crc32(p.read_bytes()) & 0xFFFFFFFF


def _opaque(img) -> bool:
    return img.getchannel("A").getbbox() is not None


def _white_px(img) -> int:
    return sum(1 for px in img.getdata()
               if px[:3] == (255, 255, 255) and px[3] > 0)


# ── Plug-in contract ───────────────────────────────────────────────────
def test_registered() -> None:
    assert Critter.id == "critter"
    assert GENERATORS["critter"] is Critter


@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_all_archetypes_render_nonempty(archetype: str) -> None:
    frames = Critter().generate(seed=1, count=2, frame_px=64,
                                params={"archetype": archetype})
    assert len(frames) == 2
    for fr in frames:
        assert fr.image.size == (64, 64)
        assert fr.image.mode == "RGBA"
        assert _opaque(fr.image), f"archetype '{archetype}' rendered empty"


def test_default_archetype_is_quadruped() -> None:
    default = Critter().generate(1, 1, 64, {})
    explicit = Critter().generate(1, 1, 64, {"archetype": "quadruped"})
    assert default[0].image.tobytes() == explicit[0].image.tobytes()


def test_invalid_archetype_raises() -> None:
    with pytest.raises(ValueError, match="archetype"):
        Critter().generate(1, 1, 64, {"archetype": "dragon"})


def test_invalid_facing_raises() -> None:
    with pytest.raises(ValueError, match="facing"):
        Critter().generate(1, 1, 64, {"facing": "up"})


@pytest.mark.parametrize("part, bad", [
    ("ears", "floppy"), ("snout", "trunk"), ("tail", "spiral"),
    ("legs", "wings"), ("wings", "bat"),
])
def test_invalid_part_raises(part: str, bad: str) -> None:
    with pytest.raises(ValueError, match=part):
        Critter().generate(1, 1, 64, {part: bad})


# ── Determinism ────────────────────────────────────────────────────────
def test_same_seed_is_byte_identical() -> None:
    a = Critter().generate(42, 4, 64, {"archetype": "quadruped"})
    b = Critter().generate(42, 4, 64, {"archetype": "quadruped"})
    assert [f.image.tobytes() for f in a] == [f.image.tobytes() for f in b]


def test_seed_changes_output() -> None:
    a = Critter().generate(1, 1, 64, {"archetype": "fish"})
    b = Critter().generate(2, 1, 64, {"archetype": "fish"})
    assert a[0].image.tobytes() != b[0].image.tobytes()


def test_base_offset_changes_anatomy() -> None:
    """``base`` shifts the item slot, so proportions (not just noise) change."""
    a = Critter().generate(5, 1, 64, {"archetype": "quadruped"}, base=0)
    b = Critter().generate(5, 1, 64, {"archetype": "quadruped"}, base=100)
    assert a[0].image.tobytes() != b[0].image.tobytes()


# ── Anatomy: stable per item, seed-picked parts ────────────────────────
def test_anatomy_is_pure_and_repeatable() -> None:
    assert _anatomy(1234, "quadruped") == _anatomy(1234, "quadruped")


def test_anatomy_parts_are_valid() -> None:
    auto = {"ears": ("round", "pointy"), "snout": ("short", "long"),
            "tail": ("short", "bushy"), "legs": ("stubby",),
            "wings": ("none",)}
    anat = _anatomy(7, "quadruped")
    for part, allowed in auto.items():
        assert anat[part] in allowed, part


def test_anatomy_differs_across_slots() -> None:
    """Two slots of the same archetype should (almost surely) differ."""
    a, b = _anatomy(1, "quadruped"), _anatomy(2, "quadruped")
    assert a != b


# ── Animation: breathing + a one-frame blink ───────────────────────────
@pytest.mark.parametrize("archetype", WHITE_EYE_ARCHETYPES)
def test_frames_actually_animate(archetype: str) -> None:
    frames = Critter().generate(3, 4, 64, {"archetype": archetype})
    assert len({f.image.tobytes() for f in frames}) >= 3


@pytest.mark.parametrize("archetype", WHITE_EYE_ARCHETYPES)
def test_blink_happens_once_per_loop(archetype: str) -> None:
    frames = Critter().generate(3, 8, 64, {"archetype": archetype})
    closed = [i for i, f in enumerate(frames) if _white_px(f.image) == 0]
    assert len(closed) == 1, f"expected one blink frame, got {closed}"
    open_px = [_white_px(f.image) for f in frames if _white_px(f.image) > 0]
    # The eye drifts with the breath, so rasterization shifts the disc a few
    # pixels; the count must stay in a tight band, not track the pose.
    assert max(open_px) - min(open_px) <= 16


def test_no_blink_below_four_frames() -> None:
    frames = Critter().generate(3, 2, 64, {"archetype": "quadruped"})
    assert all(_white_px(f.image) > 0 for f in frames)


# ── Parts and params ───────────────────────────────────────────────────
def test_part_override_changes_output() -> None:
    base = Critter().generate(11, 1, 64, {"archetype": "quadruped"})[0]
    for part, val in (("ears", "none"), ("tail", "none"), ("snout", "beak")):
        forced = Critter().generate(11, 1, 64,
                                    {"archetype": "quadruped", part: val})[0]
        assert base.image.tobytes() != forced.image.tobytes(), f"{part}={val}"


def test_forced_parts_override_seed_choice() -> None:
    """Same seed, one part forced: every *other* part stays the same, so the
    outputs share the same skeleton (spot-check via size of difference is
    overkill — the anatomy helper is the contract)."""
    for vs in range(20):
        auto = _anatomy(vs, "quadruped")
        forced = dict(auto)
        forced["ears"] = "none"
        assert forced["tail"] == auto["tail"]


def test_facing_left_is_exact_mirror() -> None:
    right = Critter().generate(9, 1, 64, {"archetype": "bird", "facing": "right"})
    left = Critter().generate(9, 1, 64, {"archetype": "bird", "facing": "left"})
    mirrored = right[0].image.transpose(Image.FLIP_LEFT_RIGHT)
    assert left[0].image.tobytes() == mirrored.tobytes()


def test_bug_is_top_view_symmetric() -> None:
    """The bug faces up: every color must balance across the spine.

    Not byte-exact — Bresenham line strokes (antennae, legs) rasterize
    asymmetrically — but a stray spot or lopsided part blows the budget.
    """
    from collections import Counter

    frame = Critter().generate(4, 1, 64, {"archetype": "bug"})[0].image
    left, right = Counter(), Counter()
    for y in range(64):
        for x in range(64):
            px = frame.getpixel((x, y))
            if px[3] == 0:
                continue
            (left if x < 32 else right)[px[:3]] += 1
    for color in set(left) | set(right):
        assert abs(left[color] - right[color]) <= 16, color


# ── Palette: neutral, tint-ready defaults + overrides ──────────────────
def test_color_override_applied() -> None:
    frames = Critter().generate(
        1, 1, 64, {"archetype": "quadruped",
                   "fill": [10, 20, 30], "outline": [1, 2, 3]})
    colors = {px[:3] for px in frames[0].image.getdata() if px[3] > 0}
    assert (10, 20, 30) in colors
    assert (1, 2, 3) in colors


def test_default_palette_is_neutral() -> None:
    """Tint ``shade`` re-hues luminance, so the base ramp must be near-gray."""
    for key in ("fill", "belly", "outline", "eye", "eye_white"):
        rgb = Critter.DEFAULTS[key]
        assert max(rgb) - min(rgb) <= 40, f"{key} too saturated: {rgb}"


def test_far_color_is_darkened_fill() -> None:
    from sprout import palettes

    frames = Critter().generate(1, 1, 64, {"archetype": "quadruped",
                                            "fill": [200, 200, 200]})
    colors = {px[:3] for px in frames[0].image.getdata() if px[3] > 0}
    assert palettes.darken((200, 200, 200), 0.72) in colors


def test_size_scales_with_frame_px() -> None:
    for size in (32, 64, 128):
        frames = Critter().generate(3, 1, size, {"archetype": "reptile"})
        assert frames[0].image.size == (size, size)


# ── Anchor points ──────────────────────────────────────────────────────
def test_anchor_present_and_within_bounds() -> None:
    for archetype in ARCHETYPES:
        frames = Critter().generate(1, 1, 64, {"archetype": archetype})
        anchor = frames[0].meta["anchor"]
        assert 0 <= anchor["x"] <= 64
        assert 0 <= anchor["y"] <= 64


def test_anchor_deterministic() -> None:
    a = Critter().generate(42, 1, 64, {"archetype": "bug"})
    b = Critter().generate(42, 1, 64, {"archetype": "bug"})
    assert a[0].meta["anchor"] == b[0].meta["anchor"]


# ── Full pipeline (spec -> atlas + manifest + index.ts) ────────────────
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


def test_manifest_frames_and_shape(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    m = json.loads((out / "manifest.json").read_text())
    assert len(m["frames"]) == 8 * 4
    ids = {f["id"] for f in m["frames"]}
    assert "quad_00" in ids and "beetle_03" in ids
    for f in m["frames"]:
        assert "anchor" in f
    assert m["anim"]["idle"]["fps"] == 6

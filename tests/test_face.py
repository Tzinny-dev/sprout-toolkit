"""Tests for the `face` generator (Fase 3: emotion faces)."""
from __future__ import annotations

import json
import zlib
from pathlib import Path

import pytest

from sprout.cli import _generate
from sprout.generators import GENERATORS
from sprout.generators.face import (BROWS, EYES, EXTRAS, HEADS, MOODS, MOUTHS,
                                    Face, _anatomy)

SPEC = Path(__file__).resolve().parents[1] / "specs" / "face.json"

ACCENT = (244, 138, 150)   # default blush / heart-eyes pink
FILL = (245, 227, 201)     # default head tone
WHITE = (255, 255, 255)    # sclera


def _crc(p: Path) -> int:
    return zlib.crc32(p.read_bytes()) & 0xFFFFFFFF


def _opaque(img) -> bool:
    return img.getchannel("A").getbbox() is not None


def _count(img, rgb) -> int:
    return sum(1 for px in img.getdata() if px[:3] == rgb and px[3] > 0)


def _distinct(frames) -> int:
    return len({f.image.tobytes() for f in frames})


# ── Plug-in contract ───────────────────────────────────────────────────
def test_registered() -> None:
    assert Face.id == "face"
    assert GENERATORS["face"] is Face


@pytest.mark.parametrize("mood", list(MOODS))
def test_all_moods_render_nonempty(mood: str) -> None:
    frames = Face().generate(seed=1, count=2, frame_px=64, params={"mood": mood})
    assert len(frames) == 2
    for fr in frames:
        assert fr.image.size == (64, 64)
        assert fr.image.mode == "RGBA"
        assert _opaque(fr.image), f"mood '{mood}' rendered empty"


def test_mood_parts_stay_within_vocab() -> None:
    """Docs promise: mood values are valid part overrides."""
    allowed = {"eyes": set(EYES[1:]), "mouth": set(MOUTHS[1:]),
               "brows": set(BROWS[1:]), "extras": set(EXTRAS[1:])}
    for mood, parts in MOODS.items():
        for name, val in parts.items():
            assert val in allowed[name], f"{mood}.{name}={val}"


# ── Validation ─────────────────────────────────────────────────────────
def test_invalid_mood_raises() -> None:
    with pytest.raises(ValueError, match="mood"):
        Face().generate(1, 1, 64, {"mood": "grumpy"})


@pytest.mark.parametrize("name, bad, vocab", [
    ("head", "long", HEADS), ("eyes", "spiral", EYES),
    ("mouth", "grill", MOUTHS), ("brows", "unibrow", BROWS),
    ("extras", "halo", EXTRAS),
])
def test_invalid_part_raises(name: str, bad: str, vocab: tuple) -> None:
    with pytest.raises(ValueError, match=name):
        Face().generate(1, 1, 64, {name: bad})


# ── Determinism ────────────────────────────────────────────────────────
def test_same_seed_is_byte_identical() -> None:
    a = Face().generate(42, 4, 64, {"mood": "joy"})
    b = Face().generate(42, 4, 64, {"mood": "joy"})
    assert [f.image.tobytes() for f in a] == [f.image.tobytes() for f in b]


def test_seed_changes_output() -> None:
    # seed 1 = wide head, seed 4 = square head (sub-pixel scale drift alone
    # can rasterize to the same bytes, so change the structure)
    a = Face().generate(1, 1, 64, {"mood": "neutral"})
    b = Face().generate(4, 1, 64, {"mood": "neutral"})
    assert a[0].image.tobytes() != b[0].image.tobytes()


def test_base_offset_changes_anatomy() -> None:
    a = Face().generate(5, 1, 64, {"mood": "happy"}, base=0)
    b = Face().generate(5, 1, 64, {"mood": "happy"}, base=100)
    assert a[0].image.tobytes() != b[0].image.tobytes()


def test_auto_mood_equals_one_of_the_presets() -> None:
    """``mood: auto`` must resolve to a real preset, nothing else."""
    auto = Face().generate(7, 1, 64, {"mood": "auto"})[0].image.tobytes()
    presets = {Face().generate(7, 1, 64, {"mood": m})[0].image.tobytes()
               for m in MOODS}
    assert auto in presets


# ── Anatomy ────────────────────────────────────────────────────────────
def test_anatomy_is_pure_and_repeatable() -> None:
    assert _anatomy(1234) == _anatomy(1234)


def test_anatomy_head_is_valid() -> None:
    assert _anatomy(7)["head"] in HEADS[1:]
    assert 0.92 <= _anatomy(7)["eye_scale"] <= 1.08


def test_anatomy_differs_across_slots() -> None:
    assert _anatomy(1) != _anatomy(2)


# ── Blink: exactly one closed frame per loop ───────────────────────────
@pytest.mark.parametrize("eyes", ("open", "wide", "wink"))
def test_blink_happens_once_per_loop(eyes: str) -> None:
    frames = Face().generate(3, 8, 64, {"mood": "happy", "eyes": eyes})
    closed = [i for i, f in enumerate(frames) if _count(f.image, WHITE) == 0]
    assert len(closed) == 1, f"expected one blink frame, got {closed}"
    assert _distinct(frames) == 2, "non-blink frames must be identical"


def test_blink_heart_eyes_once_per_loop() -> None:
    frames = Face().generate(3, 8, 64, {"mood": "happy", "eyes": "heart"})
    closed = [i for i, f in enumerate(frames) if _count(f.image, ACCENT) == 0]
    assert len(closed) == 1, f"expected one blink frame, got {closed}"
    assert _distinct(frames) == 2


@pytest.mark.parametrize("eyes", ("closed", "x", "happy"))
def test_non_blinkable_eyes_never_blink(eyes: str) -> None:
    frames = Face().generate(3, 8, 64, {"mood": "happy", "eyes": eyes})
    assert _distinct(frames) == 1


def test_no_blink_below_four_frames() -> None:
    frames = Face().generate(3, 3, 64, {"mood": "happy"})
    assert _distinct(frames) == 1


# ── Parts and moods ────────────────────────────────────────────────────
def test_mood_changes_output() -> None:
    happy = Face().generate(11, 1, 64, {"mood": "happy"})
    sad = Face().generate(11, 1, 64, {"mood": "sad"})
    assert happy[0].image.tobytes() != sad[0].image.tobytes()


@pytest.mark.parametrize("part, val", [
    ("head", "square"), ("eyes", "x"), ("mouth", "grin"),
    ("brows", "angry"), ("extras", "blush"),
])
def test_part_override_changes_output(part: str, val: str) -> None:
    base = Face().generate(11, 1, 64, {"mood": "neutral"})[0]
    forced = Face().generate(11, 1, 64, {"mood": "neutral", part: val})[0]
    assert base.image.tobytes() != forced.image.tobytes(), f"{part}={val}"


def test_wink_is_one_eyed() -> None:
    px = Face().generate(9, 1, 64, {"mood": "wink"})[0].image.load()
    left = sum(1 for y in range(64) for x in range(32) if px[x, y][:3] == WHITE)
    right = sum(1 for y in range(64) for x in range(32, 64)
                if px[x, y][:3] == WHITE)
    assert left > 0
    assert right == 0, "the winked eye must have no sclera"


def test_face_is_mirrored_around_center() -> None:
    """No extras (they break symmetry): head + eyes + mouth are symmetric.
    Not byte-exact — arc/Bresenham strokes rasterize asymmetrically — but a
    lopsided feature blows the budget. The budget scales with feature size:
    rasterization noise grows with area, while a feature drawn on one side
    only shifts its whole count to the other."""
    from collections import Counter

    frame = Face().generate(4, 1, 64, {"mood": "neutral"})[0].image
    left, right = Counter(), Counter()
    for y in range(64):
        for x in range(64):
            px = frame.getpixel((x, y))
            if px[3] == 0:
                continue
            (left if x < 32 else right)[px[:3]] += 1
    for color in set(left) | set(right):
        budget = max(16, int(0.08 * max(left[color], right[color])))
        assert abs(left[color] - right[color]) <= budget, color


# ── Palette: overrides ─────────────────────────────────────────────────
def test_color_override_applied() -> None:
    frames = Face().generate(
        1, 1, 64, {"mood": "neutral", "fill": [10, 20, 30], "eye": [1, 2, 3]})
    colors = {px[:3] for px in frames[0].image.getdata() if px[3] > 0}
    assert (10, 20, 30) in colors
    assert (1, 2, 3) in colors


def test_default_sclera_is_pure_white() -> None:
    frames = Face().generate(1, 1, 64, {"mood": "happy"})
    assert _count(frames[0].image, WHITE) > 0


def test_size_scales_with_frame_px() -> None:
    for size in (32, 64, 128):
        frames = Face().generate(3, 1, size, {"mood": "happy"})
        assert frames[0].image.size == (size, size)


def test_anchor_below_the_head() -> None:
    for mood in ("neutral", "joy", "wink"):
        anchor = Face().generate(6, 1, 64, {"mood": mood})[0].meta["anchor"]
        assert abs(anchor["x"] - 32) <= 6, mood
        assert 0.70 * 64 <= anchor["y"] <= 0.90 * 64, mood


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
    assert len(m["frames"]) == len(MOODS) + 4   # 16 moods + blink
    ids = {f["id"] for f in m["frames"]}
    assert "neutral_00" in ids and "blink_03" in ids
    for f in m["frames"]:
        assert "anchor" in f
    assert m["anim"]["blink"]["fps"] == 6
    assert m["anim"]["blink"]["frames"] == [f"blink_0{i}" for i in range(4)]

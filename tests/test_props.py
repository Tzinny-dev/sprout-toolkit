"""Tests for the `props` generator (static objects)."""
from __future__ import annotations

import json
import zlib
from pathlib import Path

import pytest
from PIL import Image

from sprout.cli import _generate
from sprout.generators import GENERATORS
from sprout.generators.props import FORMS, Props

SPEC = Path(__file__).resolve().parents[1] / "specs" / "props.json"
SPEC_OBJECTS = Path(__file__).resolve().parents[1] / "specs" / "objects.json"

ALL_KINDS = ("rock", "bush", "chest", "mushroom", "flower")
V3_KINDS = ("fruit", "sweet", "potion", "treasure", "tool", "paper", "container")
V3_FORMS = [(k, f) for k in V3_KINDS for f in FORMS[k][1:]]


def _crc(p: Path) -> int:
    return zlib.crc32(p.read_bytes()) & 0xFFFFFFFF


def _opaque(img) -> int:
    return int((img.getchannel("A").getbbox() is not None))


# ── Plug-in contract ───────────────────────────────────────────────────
def test_registered() -> None:
    assert Props.id == "props"
    assert GENERATORS["props"] is Props


def test_all_kinds_render_nonempty() -> None:
    gen = Props()
    for kind in ALL_KINDS:
        frames = gen.generate(seed=1, count=2, frame_px=64, params={"kind": kind})
        assert len(frames) == 2
        for fr in frames:
            assert fr.image.size == (64, 64)
            assert fr.image.mode == "RGBA"
            assert _opaque(fr.image), f"kind '{kind}' rendered empty"


def test_default_kind_is_rock() -> None:
    frames = Props().generate(1, 1, 64, {})
    assert _opaque(frames[0].image)


def test_invalid_kind_raises() -> None:
    with pytest.raises(ValueError, match="kind"):
        Props().generate(1, 1, 64, {"kind": "dragon"})


# ── Determinism ─────────────────────────────────────────────────────────
def test_same_seed_is_byte_identical() -> None:
    a = Props().generate(42, 3, 64, {"kind": "rock"})
    b = Props().generate(42, 3, 64, {"kind": "rock"})
    assert [f.image.tobytes() for f in a] == [f.image.tobytes() for f in b]


def test_seed_changes_output() -> None:
    a = Props().generate(1, 1, 64, {"kind": "rock"})
    b = Props().generate(2, 1, 64, {"kind": "rock"})
    assert a[0].image.tobytes() != b[0].image.tobytes()


def test_variants_differ_between_slots() -> None:
    """Each grid slot must be a distinct variant."""
    frames = Props().generate(7, 4, 64, {"kind": "bush"})
    assert len({f.image.tobytes() for f in frames}) == 4


def test_base_offset_changes_variant() -> None:
    """The ``base`` offset (global position in the sheet) varies the seed."""
    a = Props().generate(5, 1, 64, {"kind": "flower"}, base=0)
    b = Props().generate(5, 1, 64, {"kind": "flower"}, base=100)
    assert a[0].image.tobytes() != b[0].image.tobytes()


# ── Palette ────────────────────────────────────────────────────────────
def test_color_override_applied() -> None:
    frames = Props().generate(
        1, 1, 64, {"kind": "chest", "fill": [10, 20, 30], "outline": [1, 2, 3]}
    )
    colors = {px[:3] for px in frames[0].image.getdata() if px[3] > 0}
    assert (10, 20, 30) in colors
    assert (1, 2, 3) in colors


def test_size_scales_with_frame_px() -> None:
    for size in (32, 64, 128):
        frames = Props().generate(3, 1, size, {"kind": "rock"})
        assert frames[0].image.size == (size, size)


# ── Anchor points (v2) ────────────────────────────────────────────────────
def test_anchor_present_and_within_bounds() -> None:
    for kind in ALL_KINDS:
        frames = Props().generate(1, 1, 64, {"kind": kind})
        anchor = frames[0].meta["anchor"]
        assert 0 <= anchor["x"] <= 64
        assert 0 <= anchor["y"] <= 64


def test_anchor_deterministic() -> None:
    a = Props().generate(42, 1, 64, {"kind": "bush"})
    b = Props().generate(42, 1, 64, {"kind": "bush"})
    assert a[0].meta["anchor"] == b[0].meta["anchor"]


def test_anchor_follows_actual_shape() -> None:
    """The anchor follows the actual alpha bbox, not a per-kind constant: the
    `mushroom` stem falls further down than the compact `rock` body."""
    rock = Props().generate(1, 1, 64, {"kind": "rock"})[0].meta["anchor"]
    mushroom = Props().generate(1, 1, 64, {"kind": "mushroom"})[0].meta["anchor"]
    assert mushroom["y"] > rock["y"]


def test_anchor_falls_back_to_center_on_empty_frame() -> None:
    from sprout.generators.props import _anchor_from_alpha

    empty = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    assert _anchor_from_alpha(empty) == {"x": 32.0, "y": 32.0}


# ── v3 object grammar ──────────────────────────────────────────────────
def test_v3_kinds_render_nonempty() -> None:
    gen = Props()
    for kind in V3_KINDS:
        frames = gen.generate(seed=1, count=2, frame_px=64,
                              params={"kind": kind, "form": "auto"})
        assert len(frames) == 2
        for fr in frames:
            assert fr.image.size == (64, 64)
            assert _opaque(fr.image), f"kind '{kind}' rendered empty"


@pytest.mark.parametrize("kind, form", V3_FORMS)
def test_every_form_renders_nonempty(kind: str, form: str) -> None:
    for size in (32, 64, 128):
        frames = Props().generate(seed=7, count=1, frame_px=size,
                                  params={"kind": kind, "form": form})
        img = frames[0].image
        assert img.getchannel("A").getbbox() is not None, \
            f"{kind}/{form} empty at {size}px"


def test_invalid_form_raises() -> None:
    with pytest.raises(ValueError, match="form"):
        Props().generate(1, 1, 64, {"kind": "fruit", "form": "potion"})


def test_form_rejected_for_formless_kind() -> None:
    """v1 kinds must not accept a form (their output is frozen)."""
    with pytest.raises(ValueError, match="form"):
        Props().generate(1, 1, 64, {"kind": "rock", "form": "apple"})


def test_auto_form_is_one_of_the_explicit_forms() -> None:
    gen = Props()
    explicit = {gen.generate(3, 1, 64, {"kind": "fruit", "form": f})[0].image.tobytes()
                for f in FORMS["fruit"][1:]}
    picked = {gen.generate(s, 1, 64, {"kind": "fruit", "form": "auto"})[0].image.tobytes()
              for s in range(30)}
    assert picked <= explicit
    assert len(picked) >= 3, "auto must vary across seeds"


def test_form_determinism() -> None:
    a = Props().generate(42, 3, 64, {"kind": "sweet", "form": "donut"})
    b = Props().generate(42, 3, 64, {"kind": "sweet", "form": "donut"})
    assert [f.image.tobytes() for f in a] == [f.image.tobytes() for f in b]


def test_v3_color_overrides() -> None:
    frames = Props().generate(
        1, 1, 64,
        {"kind": "fruit", "form": "apple", "fill": [10, 20, 30],
         "accent": [1, 2, 3], "outline": [4, 5, 6]})
    colors = {px[:3] for px in frames[0].image.getdata() if px[3] > 0}
    assert {(10, 20, 30), (1, 2, 3), (4, 5, 6)} <= colors


def test_v3_outline_derives_from_fill() -> None:
    from sprout import palettes

    fill = (214, 64, 70)
    frames = Props().generate(1, 1, 64, {"kind": "fruit", "form": "apple",
                                         "fill": list(fill)})
    colors = {px[:3] for px in frames[0].image.getdata() if px[3] > 0}
    assert palettes.outline_color(fill) in colors


def test_v3_anchor_within_bounds() -> None:
    for kind, form in V3_FORMS:
        anchor = Props().generate(5, 1, 64,
                                  {"kind": kind, "form": form})[0].meta["anchor"]
        assert 0 <= anchor["x"] <= 64, f"{kind}/{form}"
        assert 0 <= anchor["y"] <= 64, f"{kind}/{form}"


# ── Full pipeline (spec -> atlas + manifest + index.ts) ─────────────────
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


def test_manifest_frames_have_anchor(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    m = json.loads((out / "manifest.json").read_text())
    for f in m["frames"]:
        assert "anchor" in f, f"frame '{f['id']}' missing anchor"
        assert isinstance(f["anchor"]["x"], (int, float))
        assert isinstance(f["anchor"]["y"], (int, float))


def test_manifest_frames_and_shape(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    m = json.loads((out / "manifest.json").read_text())
    # 6 rock + 6 bush + 4 chest + 4 mushroom + 6 flower = 26
    assert len(m["frames"]) == 26
    ids = {f["id"] for f in m["frames"]}
    assert "rock_00" in ids and "rock_05" in ids
    assert "flower_05" in ids
    assert m["schema"] == "sprout/manifest@0"
    assert m["units"]["framePx"] == 64
    assert m["meta"]["generator"]["name"] == "sprout"


def test_skip_existing_idempotent(tmp_path: Path) -> None:
    out = tmp_path / "out"
    r1 = _generate(SPEC, out, None, False)
    r2 = _generate(SPEC, out, None, True)
    assert r1["skipped"] is False
    assert r2["skipped"] is True
    assert r1["crc"] == r2["crc"]


def test_objects_spec_generates_all_outputs(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC_OBJECTS, out, None, False)
    assert (out / "atlas.png").is_file()
    assert (out / "manifest.json").is_file()
    assert (out / "index.ts").is_file()


def test_objects_spec_deterministic(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    _generate(SPEC_OBJECTS, a, None, False)
    _generate(SPEC_OBJECTS, b, None, False)
    assert _crc(a / "atlas.png") == _crc(b / "atlas.png")
    assert (a / "manifest.json").read_bytes() == (b / "manifest.json").read_bytes()


def test_objects_spec_covers_every_form(tmp_path: Path) -> None:
    """The spec pins one item per form — the grammar's showcase/coverage."""
    out = tmp_path / "out"
    _generate(SPEC_OBJECTS, out, None, False)
    m = json.loads((out / "manifest.json").read_text())
    ids = {f["id"].rsplit("_", 1)[0] for f in m["frames"]}
    assert ids == {form for _, form in V3_FORMS}
    assert len(m["frames"]) == len(V3_FORMS)
    for f in m["frames"]:
        assert "anchor" in f

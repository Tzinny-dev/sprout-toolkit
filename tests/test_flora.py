"""Tests for the `flora` generator (Fase 3: trees + forest-floor plants)."""
from __future__ import annotations

import json
import zlib
from pathlib import Path

import pytest

from sprout.cli import _generate
from sprout.generators import GENERATORS
from sprout.generators.flora import AGES, CANOPY, FORMS, KINDS, TRUNK, Flora, _anatomy

SPEC = Path(__file__).resolve().parents[1] / "specs" / "flora.json"


def _crc(p: Path) -> int:
    return zlib.crc32(p.read_bytes()) & 0xFFFFFFFF


def _opaque(img) -> bool:
    return img.getchannel("A").getbbox() is not None


def _colors(img) -> set:
    return {px[:3] for px in img.getdata() if px[3] > 0}


def _distinct(frames) -> int:
    return len({f.image.tobytes() for f in frames})


# ── Plug-in contract ───────────────────────────────────────────────────
def test_registered() -> None:
    assert Flora.id == "flora"
    assert GENERATORS["flora"] is Flora


@pytest.mark.parametrize("kind", KINDS)
def test_all_kinds_render_nonempty(kind: str) -> None:
    frames = Flora().generate(seed=1, count=2, frame_px=64, params={"kind": kind})
    assert len(frames) == 2
    for fr in frames:
        assert fr.image.size == (64, 64)
        assert fr.image.mode == "RGBA"
        assert _opaque(fr.image), f"kind '{kind}' rendered empty"


@pytest.mark.parametrize("canopy", CANOPY[1:])
def test_all_canopies_render_nonempty(canopy: str) -> None:
    frames = Flora().generate(1, 1, 64, {"kind": "tree", "canopy": canopy})
    assert _opaque(frames[0].image)


@pytest.mark.parametrize("trunk", TRUNK[1:])
def test_all_trunks_render_nonempty(trunk: str) -> None:
    frames = Flora().generate(1, 1, 64, {"kind": "tree", "trunk": trunk})
    assert _opaque(frames[0].image)


@pytest.mark.parametrize("form", FORMS[1:])
def test_all_plant_forms_render_nonempty(form: str) -> None:
    frames = Flora().generate(1, 1, 64, {"kind": "plant", "form": form})
    assert _opaque(frames[0].image)


# ── Validation ─────────────────────────────────────────────────────────
def test_invalid_kind_raises() -> None:
    with pytest.raises(ValueError, match="kind"):
        Flora().generate(1, 1, 64, {"kind": "mushroom"})


@pytest.mark.parametrize("name, bad", [
    ("canopy", "spherical"), ("trunk", "spiral"), ("age", "ancient"),
    ("form", "cactus"),
])
def test_invalid_style_raises(name: str, bad: str) -> None:
    with pytest.raises(ValueError, match=name):
        Flora().generate(1, 1, 64, {name: bad})


def test_invalid_sway_raises() -> None:
    with pytest.raises(ValueError, match="sway"):
        Flora().generate(1, 1, 64, {"sway": "yes"})


# ── Determinism ────────────────────────────────────────────────────────
def test_same_seed_is_byte_identical() -> None:
    a = Flora().generate(42, 4, 64, {"canopy": "round", "sway": True})
    b = Flora().generate(42, 4, 64, {"canopy": "round", "sway": True})
    assert [f.image.tobytes() for f in a] == [f.image.tobytes() for f in b]


def test_seed_changes_output() -> None:
    a = Flora().generate(1, 1, 64, {"kind": "plant"})
    b = Flora().generate(2, 1, 64, {"kind": "plant"})
    assert a[0].image.tobytes() != b[0].image.tobytes()


def test_base_offset_changes_anatomy() -> None:
    a = Flora().generate(5, 1, 64, {"kind": "tree"}, base=0)
    b = Flora().generate(5, 1, 64, {"kind": "tree"}, base=100)
    assert a[0].image.tobytes() != b[0].image.tobytes()


# ── Anatomy: stable per item, seed-picked styles ───────────────────────
def test_anatomy_is_pure_and_repeatable() -> None:
    assert _anatomy(1234, "tree") == _anatomy(1234, "tree")
    assert _anatomy(1234, "plant") == _anatomy(1234, "plant")


def test_anatomy_styles_are_valid() -> None:
    tree = _anatomy(7, "tree")
    assert tree["canopy"] in CANOPY[1:]
    assert tree["trunk"] in TRUNK[1:]
    plant = _anatomy(9, "plant")
    assert plant["form"] in FORMS[1:]


def test_anatomy_differs_across_slots() -> None:
    a, b = _anatomy(1, "tree"), _anatomy(2, "tree")
    assert a != b


def test_trunk_style_changes_output() -> None:
    """Gnarled shows lean+kink; the same anatomy as straight must differ."""
    gnarled = Flora().generate(3, 1, 64, {"trunk": "gnarled"})
    straight = Flora().generate(3, 1, 64, {"trunk": "straight"})
    assert gnarled[0].image.tobytes() != straight[0].image.tobytes()


# ── Maturity stages ────────────────────────────────────────────────────
@pytest.mark.parametrize("age", AGES[1:])
def test_all_ages_render_nonempty(age: str) -> None:
    frame = Flora().generate(2, 1, 64, {"kind": "tree", "age": age,
                                        "canopy": "round"})[0]
    assert frame.image.getchannel("A").getbbox() is not None


def test_age_changes_output() -> None:
    base = {"kind": "tree", "canopy": "round", "trunk": "straight"}
    seen = {Flora().generate(3, 1, 64, {**base, "age": a})[0].image.tobytes()
            for a in AGES[1:]}
    assert len(seen) == len(AGES) - 1


def test_stage_scales_the_silhouette() -> None:
    """A sapling is shorter than a mature tree; an old one is wider and
    carries more mass, not just more height."""
    base = {"kind": "tree", "canopy": "round", "trunk": "straight"}

    def metrics(age: str) -> tuple[float, float, float]:
        h = w = area = 0.0
        for seed in range(1, 21):
            img = Flora().generate(seed, 1, 64, {**base, "age": age})[0].image
            x0, y0, x1, y1 = img.getbbox()
            h += y1 - y0
            w += x1 - x0
            area += sum(1 for v in img.getchannel("A").getdata() if v > 0)
        n = 20
        return h / n, w / n, area / n

    sap_h, _, sap_a = metrics("sapling")
    mat_h, mat_w, mat_a = metrics("mature")
    old_h, old_w, old_a = metrics("old")

    assert sap_h < mat_h, "a sapling is not shorter than a mature tree"
    assert sap_a < mat_a, "a sapling is not lighter than a mature tree"
    assert old_w > mat_w, "an old tree is not broader than a mature one"
    assert old_a > mat_a, "an old tree carries no more mass than a mature one"


def test_stage_keeps_the_frame_inside() -> None:
    """Bigger stages grow the canopy downward, not past the frame."""
    for age in AGES[1:]:
        for canopy in CANOPY[1:]:
            for seed in (1, 4, 9):
                img = Flora().generate(seed, 1, 64,
                                       {"kind": "tree", "age": age,
                                        "canopy": canopy})[0].image
                x0, y0, x1, y1 = img.getbbox()
                assert y0 >= 5, f"{age}/{canopy} touches the top ({y0})"
                assert x0 >= 0 and x1 <= 64, f"{age}/{canopy} overflows a side"
                assert y1 <= 64, f"{age}/{canopy} overflows the bottom ({y1})"


def test_forced_age_overrides_the_seed() -> None:
    """The stage scales the proportions, so it has to reach ``_anatomy``
    instead of relabelling a finished tree."""
    sapling = _anatomy(7, "tree", "sapling")
    mature = _anatomy(7, "tree", "mature")
    assert sapling["age"] == "sapling" and mature["age"] == "mature"
    # everything else about the seed is untouched
    assert sapling["canopy"] == mature["canopy"]
    assert sapling["trunk"] == mature["trunk"]
    # only the scaled proportions differ
    assert sapling["trunk_h"] < mature["trunk_h"]
    assert sapling["canopy_r"] < mature["canopy_r"]
    assert sapling["trunk_w"] < mature["trunk_w"]


def test_auto_age_is_always_a_known_stage() -> None:
    for vs in range(50):
        assert _anatomy(vs, "tree")["age"] in AGES[1:]


# ── Sway animation ─────────────────────────────────────────────────────
def test_sway_animates_tree() -> None:
    frames = Flora().generate(3, 4, 64, {"sway": True})
    assert _distinct(frames) >= 3


def test_sway_animates_plant() -> None:
    frames = Flora().generate(3, 4, 64, {"kind": "plant", "form": "grass",
                                         "sway": True})
    assert _distinct(frames) >= 3


def test_no_sway_frames_are_identical() -> None:
    frames = Flora().generate(3, 4, 64, {"kind": "tree"})
    assert _distinct(frames) == 1


# ── Layout: margin above, ground below ─────────────────────────────────
@pytest.mark.parametrize("canopy", CANOPY[1:])
def test_canopy_keeps_top_margin(canopy: str) -> None:
    frame = Flora().generate(2, 1, 64, {"kind": "tree", "canopy": canopy})[0]
    top = frame.image.getchannel("A").getbbox()[1]
    assert top >= 5, f"{canopy} canopy touches the frame top ({top})"


@pytest.mark.parametrize("kind", KINDS)
def test_sits_on_the_ground(kind: str) -> None:
    frame = Flora().generate(4, 1, 64, {"kind": kind})[0]
    bottom = frame.image.getchannel("A").getbbox()[3]
    assert bottom >= 0.80 * 64


def test_anchor_near_bottom_center() -> None:
    for kind in KINDS:
        anchor = Flora().generate(6, 1, 64, {"kind": kind})[0].meta["anchor"]
        assert abs(anchor["x"] - 32) <= 14, kind
        assert 0.78 * 64 <= anchor["y"] <= 0.95 * 64, kind


# ── Palette: overrides + derived outlines ──────────────────────────────
def test_color_override_applied() -> None:
    frames = Flora().generate(
        1, 1, 64, {"kind": "tree", "fill": [10, 20, 30], "bark": [40, 50, 60]})
    colors = _colors(frames[0].image)
    assert (10, 20, 30) in colors
    assert (40, 50, 60) in colors


def test_outlines_derive_from_roles() -> None:
    from sprout import palettes

    frames = Flora().generate(1, 1, 64, {"kind": "tree", "fill": [200, 200, 200]})
    colors = _colors(frames[0].image)
    assert palettes.outline_color((200, 200, 200)) in colors


def test_explicit_outline_applies_to_foliage_and_bark() -> None:
    frames = Flora().generate(
        1, 1, 64, {"kind": "tree", "fill": [10, 20, 30], "bark": [40, 50, 60],
                   "outline": [1, 2, 3]})
    colors = _colors(frames[0].image)
    assert (1, 2, 3) in colors
    # with an explicit outline there is no derived dark-green ring
    from sprout import palettes
    assert palettes.outline_color((10, 20, 30)) not in colors


def test_plant_color_override_applied() -> None:
    frames = Flora().generate(
        1, 1, 64, {"kind": "plant", "form": "sprout", "fill": [7, 8, 9]})
    assert (7, 8, 9) in _colors(frames[0].image)


def test_size_scales_with_frame_px() -> None:
    for size in (32, 64, 128):
        frames = Flora().generate(3, 1, size, {"kind": "tree"})
        assert frames[0].image.size == (size, size)


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
    items = json.loads(SPEC.read_text())["items"]
    assert len(m["frames"]) == sum(it["frames"] for it in items)
    ids = {f["id"] for f in m["frames"]}
    assert "oak_00" in ids and "oak_03" in ids
    assert "grass_03" in ids and "blossom_00" in ids
    for f in m["frames"]:
        assert "anchor" in f
    assert m["anim"]["sway"]["fps"] == 4
    assert m["anim"]["sway"]["frames"] == [f"oak_0{i}" for i in range(4)]
    assert m["anim"]["grass_sway"]["fps"] == 4

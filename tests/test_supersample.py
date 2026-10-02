"""Tests for `supersample`: render N x, box-filter back down.

The feature exists because PIL's drawing primitives are aliased, so raising
`framePx` and sampling with `nearest` buys nothing (point sampling drops the
extra pixels instead of averaging them). Every generator already scales its
geometry with `frame_px`, so supersampling only has to render bigger and
reduce -- but that makes frame-pixel metadata come back at the wrong scale,
which is what most of these tests guard.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from sprout.cli import app
from sprout.exporter import build_sheet, render_items
from sprout.spec import load_spec

SPECS = Path(__file__).resolve().parents[1] / "specs"
runner = CliRunner()


def _spec_copy(tmp_path: Path, name: str, supersample: int) -> Path:
    """A copy of a bundled spec with `layout.supersample` forced.

    The shipped specs ask for 4, so a test about N=1 has to say so rather than
    rely on the default staying where it was.
    """
    raw = json.loads((SPECS / f"{name}.json").read_text())
    raw["layout"]["supersample"] = supersample
    out = tmp_path / f"{name}-{supersample}.json"
    out.write_text(json.dumps(raw, indent=2) + "\n")
    return out


def _gen_path(spec: Path, tmp_path: Path, *extra: str) -> tuple[Image.Image, dict]:
    out = tmp_path / (spec.stem + "-" + ("-".join(extra) or "default"))
    result = runner.invoke(app, ["generate", str(spec), "-o", str(out), *extra])
    assert result.exit_code == 0, result.output
    return (Image.open(out / "atlas.png").convert("RGBA"),
            json.loads((out / "manifest.json").read_text()))


def _gen(spec: str, tmp_path: Path, *extra: str) -> tuple[Image.Image, dict]:
    return _gen_path(SPECS / f"{spec}.json", tmp_path, *extra)


def _partial_alpha(img: Image.Image) -> int:
    """Pixels with 0 < alpha < 255 -- the ones antialiasing had to create."""
    hist = img.getchannel("A").histogram()
    return sum(hist[1:255])


# ── the atlas is unchanged in logical terms ───────────────────────────────────

def test_supersample_one_is_the_pre_flag_bytes(tmp_path: Path) -> None:
    """N=1 must not touch a byte: it divides nothing and filters nothing.

    Pinned against a spec that *asks* for 1, so this keeps meaning the same
    thing after the shipped specs moved to 4.
    """
    spec = _spec_copy(tmp_path, "critter", 1)
    a, _ = _gen_path(spec, tmp_path)
    b, _ = _gen_path(spec, tmp_path, "--supersample", "1")
    assert a.tobytes() == b.tobytes()
    assert sum(a.getchannel("A").histogram()[1:255]) == 0


def test_supersample_one_keeps_anchor_ints(tmp_path: Path) -> None:
    """Regression: `56 / 1` is `56.0`, which is a different manifest.

    An anchor coordinate is an int when it comes straight from the alpha
    bbox's exclusive edge. Dividing by an explicit 1 would float it and
    rewrite the manifest of an atlas whose pixels never moved.
    """
    _, m1 = _gen("critter", tmp_path, "--supersample", "1")
    anchor = m1["frames"][0]["anchor"]
    assert isinstance(anchor["y"], int), "int anchor became a float at N=1"


def test_supersample_keeps_the_sheet_and_records_logical(tmp_path: Path) -> None:
    """The emitted atlas is `framePx` either way; only the render was bigger."""
    _, m1 = _gen("critter", tmp_path)
    img4, m4 = _gen("critter", tmp_path, "--supersample", "4")
    assert m1["units"]["framePx"] == m4["units"]["framePx"] == 64
    assert m4["files"]["atlasW"] == m1["files"]["atlasW"]
    assert m4["files"]["atlasH"] == m1["files"]["atlasH"]
    assert img4.size == (m1["files"]["atlasW"], m1["files"]["atlasH"])
    for r1, r4 in zip(m1["frames"], m4["frames"], strict=True):
        assert (r1["x"], r1["y"], r1["w"], r1["h"]) == (r4["x"], r4["y"], r4["w"], r4["h"])


# ── frame-pixel metadata is divided back down ────────────────────────────────

def test_supersample_divides_anchors(tmp_path: Path) -> None:
    """An anchor is measured in frame pixels, so N=4 must bring it back to 1x.

    The tolerance is 1 px because supersampling genuinely moves the ground
    line: a partially covered border pixel that was empty at N=1 survives the
    box filter, so the alpha bbox grows by up to a pixel. That is the honest
    new ground contact, not a rounding error to be engineered away.
    """
    _, m1 = _gen("critter", tmp_path)
    _, m4 = _gen("critter", tmp_path, "--supersample", "4")
    worst = 0.0
    for r1, r4 in zip(m1["frames"], m4["frames"], strict=True):
        for k in ("x", "y"):
            worst = max(worst, abs(r1["anchor"][k] - r4["anchor"][k]))
    assert worst <= 1.0, f"anchor drifted {worst} px at N=4"
    # and it is genuinely divided, not left at the N=4 measurement
    assert m4["frames"][0]["anchor"]["x"] < m1["frames"][0]["anchor"]["x"] + 4


def test_supersample_divides_font_advances(tmp_path: Path) -> None:
    """Font `advance` is the one metric a generator reports in frame pixels."""
    _, m1 = _gen("font", tmp_path)
    _, m4 = _gen("font", tmp_path, "--supersample", "4")
    item1 = next(iter(m1["font"]["items"].values()))
    item4 = next(iter(m4["font"]["items"].values()))
    assert (item1["ascent"], item1["descent"]) == (item4["ascent"], item4["descent"])
    for ch, g1 in item1["glyphs"].items():
        assert g1["advance"] == item4["glyphs"][ch]["advance"], ch


# ── the point of the flag ─────────────────────────────────────────────────────

def test_supersample_antialiases_edges(tmp_path: Path) -> None:
    """N=1 cannot produce a partial alpha; N=4 must produce plenty."""
    img1, _ = _gen("critter", tmp_path, "--supersample", "1")
    img4, _ = _gen("critter", tmp_path, "--supersample", "4")
    assert _partial_alpha(img1) == 0, "N=1 produced antialiasing it cannot have"
    assert _partial_alpha(img4) > 1000


def test_supersample_quality_saturates(tmp_path: Path) -> None:
    """4x captures most of the benefit; 8x is mostly wasted memory.

    Guards against a change that silently makes supersampling linear in cost
    while barely improving the result.
    """
    counts = {}
    for n in (2, 4, 8):
        img, _ = _gen("critter", tmp_path, "--supersample", str(n))
        counts[n] = _partial_alpha(img)
    assert counts[2] < counts[4] < counts[8]
    gain_2_to_4 = counts[4] - counts[2]
    gain_4_to_8 = counts[8] - counts[4]
    assert gain_2_to_4 > 2 * gain_4_to_8, f"4x -> 8x barely improved: {counts}"


def test_supersample_is_deterministic(tmp_path: Path) -> None:
    a, ma = _gen("critter", tmp_path / "a", "--supersample", "4")
    b, mb = _gen("critter", tmp_path / "b", "--supersample", "4")
    assert a.tobytes() == b.tobytes()
    assert ma == mb


# ── library-level contract ────────────────────────────────────────────────────

def test_library_api_follows_the_spec_not_a_hardcoded_one() -> None:
    """No-argument calls must honour layout.supersample, not default to 1.

    A library caller gets the atlas the CLI would produce from that spec; only
    an explicit argument overrides it.
    """
    spec = load_spec(SPECS / "critter.json")
    assert spec.layout.supersample == 4, "shipped specs are expected to smooth"
    implicit, records = build_sheet(spec, render_items(spec))
    explicit, records1 = build_sheet(spec, render_items(spec, 4), 4)
    assert implicit.tobytes() == explicit.tobytes()
    assert records == records1
    aliased, _ = build_sheet(spec, render_items(spec, 1), 1)
    assert aliased.tobytes() != implicit.tobytes()


def test_sheet_reduces_to_an_integer_multiple() -> None:
    """A non-integer reduction would leave ragged frame borders."""
    spec = load_spec(SPECS / "critter.json")
    for n in (1, 2, 3, 4, 5):
        img, records = build_sheet(spec, render_items(spec, n), n)
        cols, rows = spec.layout.cols, spec.layout.resolve_rows(spec.total_frames)
        assert img.size == (cols * spec.layout.frame_px, rows * spec.layout.frame_px), n
        assert len(records) == spec.total_frames


# ── layout.supersample: the decision lives in the spec ────────────────────────

def test_spec_field_carries_the_decision(tmp_path: Path) -> None:
    """No flag, no surprise: the atlas follows layout.supersample."""
    spec = load_spec(SPECS / "critter.json")
    assert spec.layout.supersample == 4
    from_flag, _ = _gen("critter", tmp_path, "--supersample", "4")
    from_spec, _ = _gen("critter", tmp_path)
    assert from_flag.tobytes() == from_spec.tobytes()


def test_spec_field_defaults_to_one(tmp_path: Path) -> None:
    """Omitting the field must stay byte-identical to the pre-feature output."""
    raw = json.loads((SPECS / "critter.json").read_text())
    del raw["layout"]["supersample"]
    path = tmp_path / "no-supersample.json"
    path.write_text(json.dumps(raw, indent=2) + "\n")
    img, _ = _gen_path(path, tmp_path)
    assert _partial_alpha(img) == 0


def test_flag_overrides_the_spec_both_ways(tmp_path: Path) -> None:
    """--supersample 1 can un-smooth a spec that asks for 4, and vice versa."""
    smoothed, _ = _gen("critter", tmp_path)
    forced_off, _ = _gen("critter", tmp_path, "--supersample", "1")
    assert _partial_alpha(smoothed) > 1000
    assert _partial_alpha(forced_off) == 0
    spec_off = _spec_copy(tmp_path, "critter", 1)
    forced_on, _ = _gen_path(spec_off, tmp_path, "--supersample", "4")
    assert _partial_alpha(forced_on) > 1000


@pytest.mark.parametrize("bad", [0, 9, -1])
def test_spec_field_is_validated(tmp_path: Path, bad: int) -> None:
    raw = json.loads((SPECS / "critter.json").read_text())
    raw["layout"]["supersample"] = bad
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw, indent=2) + "\n")
    result = runner.invoke(app, ["generate", str(path), "-o", str(tmp_path / "o")])
    assert result.exit_code != 0
    assert "layout.supersample must be 1..8" in result.output


def test_batch_exposes_supersample(tmp_path: Path) -> None:
    """The gap that started this: batch could not supersample at all."""
    src = tmp_path / "specs"
    src.mkdir()
    for n in ("critter", "face"):
        raw = json.loads((SPECS / f"{n}.json").read_text())
        raw["layout"]["supersample"] = 1
        raw["files"]["atlas"] = f"{n}.png"
        (src / f"{n}.json").write_text(json.dumps(raw, indent=2) + "\n")
    # the subdirectory is the spec's `name` (critter.json -> critter_atlas)
    sub = "critter_atlas"
    ok = runner.invoke(app, ["batch", str(src), "-o", str(tmp_path / "plain")])
    assert ok.exit_code == 0, ok.output
    assert _partial_alpha(
        Image.open(tmp_path / "plain" / sub / "critter.png").convert("RGBA")) == 0
    ss = runner.invoke(app, ["batch", str(src), "-o", str(tmp_path / "ss"),
                             "--supersample", "4"])
    assert ss.exit_code == 0, ss.output
    assert _partial_alpha(
        Image.open(tmp_path / "ss" / sub / "critter.png").convert("RGBA")) > 1000


def test_supersample_is_recorded_as_provenance(tmp_path: Path) -> None:
    """The factor actually used, so changed bytes can be explained later.

    Provenance rather than `units`, because `units` is the contract for
    drawing the atlas and supersampling does not change it.
    """
    _, m = _gen("critter", tmp_path)
    assert m["meta"]["provenance"]["supersample"] == 4
    assert "supersample" not in m["units"]
    _, off = _gen("critter", tmp_path, "--supersample", "1")
    assert off["meta"]["provenance"]["supersample"] == 1, "flag override not recorded"
    _, eight = _gen("critter", tmp_path, "--supersample", "8")
    assert eight["meta"]["provenance"]["supersample"] == 8


# ── batch -o nests per spec instead of overwriting ────────────────────────────

def _batch_specs(tmp_path: Path, specs: list[tuple[str, str]],
                 atlas_name: str = "atlas.png") -> Path:
    """Write spec files as (file stem, spec name) pairs.

    They are separate on purpose: two files can share a spec `name`, and that
    is exactly the collision `batch --out` has to refuse.
    """
    src = tmp_path / "bspecs"
    src.mkdir(exist_ok=True)
    for stem, name in specs:
        raw = json.loads((SPECS / "critter.json").read_text())
        raw["name"] = name
        raw["files"]["atlas"] = atlas_name
        (src / f"{stem}.json").write_text(json.dumps(raw, indent=2) + "\n")
    return src


def test_batch_out_nests_per_spec_instead_of_overwriting(tmp_path: Path) -> None:
    """The bug that started this: every bundled spec writes `atlas.png`.

    With a shared --out they all landed in the same directory, so a 13-spec
    batch reported 13/13 ok and left one atlas holding only the last spec.
    """
    src = _batch_specs(tmp_path, [(n, n) for n in ("one", "two", "three")])
    out = tmp_path / "bout"
    result = runner.invoke(app, ["batch", str(src), "-o", str(out)])
    assert result.exit_code == 0, result.output
    atlases = sorted(p.relative_to(out).as_posix() for p in out.rglob("atlas.png"))
    assert atlases == ["one/atlas.png", "three/atlas.png", "two/atlas.png"]
    for name in ("one", "two", "three"):
        assert json.loads(
            (out / name / "manifest.json").read_text())["name"] == name


def test_batch_out_refuses_duplicate_spec_names(tmp_path: Path) -> None:
    """Nesting can still collide, so it must fail before writing anything."""
    src = _batch_specs(tmp_path, [("a", "same"), ("b", "same")])
    out = tmp_path / "clash"
    result = runner.invoke(app, ["batch", str(src), "-o", str(out)])
    assert result.exit_code == 1
    assert "share a name" in result.output
    assert not out.exists(), "nothing should be written when the batch is rejected"


def test_batch_without_out_still_writes_beside_each_spec(tmp_path: Path) -> None:
    """No --out means no shared directory, so nesting does not apply."""
    src = _batch_specs(tmp_path, [("solo", "solo")])
    result = runner.invoke(app, ["batch", str(src)])
    assert result.exit_code == 0, result.output
    assert (src / "atlas.png").is_file()
    assert not (src / "solo").exists()


def test_batch_nested_output_is_supersampled_from_the_spec(tmp_path: Path) -> None:
    src = tmp_path / "ssspecs"
    src.mkdir()
    for n in ("a", "b"):
        raw = json.loads((SPECS / "critter.json").read_text())
        raw["name"] = n
        raw["files"]["atlas"] = f"{n}.png"
        (src / f"{n}.json").write_text(json.dumps(raw, indent=2) + "\n")
    result = runner.invoke(app, ["batch", str(src), "-o", str(tmp_path / "ssout")])
    assert result.exit_code == 0, result.output
    for n in ("a", "b"):
        img = Image.open(tmp_path / "ssout" / n / f"{n}.png").convert("RGBA")
        assert _partial_alpha(img) > 1000, n
        assert json.loads(
            (tmp_path / "ssout" / n / "manifest.json").read_text()
        )["meta"]["provenance"]["supersample"] == 4


# ── validation ────────────────────────────────────────────────────────────────

def test_supersample_rejects_out_of_range(tmp_path: Path) -> None:
    for bad in ("0", "9"):
        result = runner.invoke(app, ["generate", str(SPECS / "critter.json"),
                                     "-o", str(tmp_path), "--supersample", bad])
        assert result.exit_code != 0, bad
        assert "invalid --supersample" in result.output


def test_supersample_works_with_tiers(tmp_path: Path) -> None:
    """--tiers threads the flag through each size."""
    result = runner.invoke(app, ["generate", str(SPECS / "critter.json"),
                                 "-o", str(tmp_path / "t"), "--tiers", "32,64",
                                 "--supersample", "4"])
    assert result.exit_code == 0, result.output
    for px in (32, 64):
        img = Image.open(tmp_path / "t" / str(px) / "atlas.png")
        assert img.size[0] % px == 0
        assert _partial_alpha(img) > 0
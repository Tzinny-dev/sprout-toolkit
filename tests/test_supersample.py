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

from PIL import Image
from typer.testing import CliRunner

from sprout.cli import app
from sprout.exporter import build_sheet, render_items
from sprout.spec import load_spec

SPECS = Path(__file__).resolve().parents[1] / "specs"
runner = CliRunner()


def _gen(spec: str, tmp_path: Path, *extra: str) -> tuple[Image.Image, dict]:
    out = tmp_path / f"{spec}-{' '.join(extra) or 'n1'}".replace("/", "_")
    result = runner.invoke(app, ["generate", str(SPECS / f"{spec}.json"),
                                 "-o", str(out), *extra])
    assert result.exit_code == 0, result.output
    return (Image.open(out / "atlas.png").convert("RGBA"),
            json.loads((out / "manifest.json").read_text()))


def _partial_alpha(img: Image.Image) -> int:
    """Pixels with 0 < alpha < 255 -- the ones antialiasing had to create."""
    hist = img.getchannel("A").histogram()
    return sum(hist[1:255])


# ── the atlas is unchanged in logical terms ───────────────────────────────────

def test_supersample_one_matches_the_default_exactly(tmp_path: Path) -> None:
    """N=1 must not touch a byte: the flag defaults to 1 and divides nothing."""
    a, _ = _gen("critter", tmp_path)
    b, _ = _gen("critter", tmp_path, "--supersample", "1")
    assert a.tobytes() == b.tobytes()


def test_supersample_one_keeps_anchor_ints(tmp_path: Path) -> None:
    """Regression: `56 / 1` is `56.0`, which is a different manifest.

    An anchor coordinate is an int when it comes straight from the alpha
    bbox's exclusive edge. Dividing by an explicit 1 would float it and
    rewrite the manifest of an atlas whose pixels never moved.
    """
    _, m1 = _gen("critter", tmp_path)
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
    img1, _ = _gen("critter", tmp_path)
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

def test_library_api_defaults_to_one() -> None:
    spec = load_spec(SPECS / "critter.json")
    plain, records = build_sheet(spec, render_items(spec))
    ss1, records1 = build_sheet(spec, render_items(spec, 1), 1)
    assert plain.tobytes() == ss1.tobytes()
    assert records == records1


def test_sheet_reduces_to_an_integer_multiple() -> None:
    """A non-integer reduction would leave ragged frame borders."""
    spec = load_spec(SPECS / "critter.json")
    for n in (1, 2, 3, 4, 5):
        img, records = build_sheet(spec, render_items(spec, n), n)
        cols, rows = spec.layout.cols, spec.layout.resolve_rows(spec.total_frames)
        assert img.size == (cols * spec.layout.frame_px, rows * spec.layout.frame_px), n
        assert len(records) == spec.total_frames


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
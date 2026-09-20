"""Tests del generador `font` (bitmap font desde TTF)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sprout.cli import _generate
from sprout.generators import GENERATORS
from sprout.generators.font import DEFAULT_CHARS, Font

SPEC = Path(__file__).resolve().parents[1] / "specs" / "font.json"


def _opaque(img) -> bool:
    return img.getchannel("A").getbbox() is not None


# ── Contrato del plug-in ────────────────────────────────────────────────
def test_registered() -> None:
    assert Font.id == "font"
    assert GENERATORS["font"] is Font


def test_default_charset_is_ascii_printable() -> None:
    assert len(DEFAULT_CHARS) == 95
    assert DEFAULT_CHARS[0] == " "
    assert DEFAULT_CHARS[-1] == "~"


def test_frames_must_match_chars_length() -> None:
    with pytest.raises(ValueError, match="95"):
        Font().generate(1, 10, 48, {})


def test_custom_chars_subset() -> None:
    frames = Font().generate(1, 2, 48, {"chars": "AB"})
    assert len(frames) == 2
    assert [fr.meta["char"] for fr in frames] == ["A", "B"]
    for fr in frames:
        assert _opaque(fr.image)


# ── Espacio: vacío a propósito, no un bug ────────────────────────────────
def test_space_glyph_is_empty() -> None:
    frames = Font().generate(1, 95, 48, {})
    space = next(fr for fr in frames if fr.meta["char"] == " ")
    assert not _opaque(space.image)


def test_printable_glyphs_are_nonempty() -> None:
    frames = Font().generate(1, 95, 48, {})
    for fr in frames:
        if fr.meta["char"] == " ":
            continue
        assert _opaque(fr.image), f"carácter '{fr.meta['char']}' renderizó vacío"


# ── Metadata ─────────────────────────────────────────────────────────────
def test_meta_has_char_and_advance() -> None:
    frames = Font().generate(1, 2, 48, {"chars": "AB"})
    for fr in frames:
        assert fr.meta["char"] in "AB"
        assert fr.meta["advance"] > 0


# ── Determinismo (sin dependencia del seed) ──────────────────────────────
def test_deterministic_regardless_of_seed() -> None:
    a = Font().generate(1, 2, 48, {"chars": "Aa"})
    b = Font().generate(999, 2, 48, {"chars": "Aa"})
    assert [f.image.tobytes() for f in a] == [f.image.tobytes() for f in b]


# ── Paleta ───────────────────────────────────────────────────────────────
def test_default_fill_is_white() -> None:
    frames = Font().generate(1, 1, 48, {"chars": "A"})
    colors = {px[:3] for px in frames[0].image.getdata() if px[3] > 0}
    assert (255, 255, 255) in colors


def test_fill_override_applied() -> None:
    frames = Font().generate(1, 1, 48, {"chars": "A", "fill": [10, 20, 30]})
    colors = {px[:3] for px in frames[0].image.getdata() if px[3] > 0}
    assert (10, 20, 30) in colors


# ── font_path inválido ────────────────────────────────────────────────────
def test_invalid_font_path_raises() -> None:
    with pytest.raises(ValueError, match="font_path"):
        Font().generate(1, 1, 48, {"chars": "A", "font_path": "/no/existe.ttf"})


# ── Pipeline completo (spec -> atlas + manifest + index.ts) ─────────────
def test_spec_generates_all_outputs(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    assert (out / "atlas.png").is_file()
    assert (out / "manifest.json").is_file()
    assert (out / "index.ts").is_file()


def test_manifest_font_block(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    m = json.loads((out / "manifest.json").read_text())
    font_block = m["font"]["items"]["hud"]
    assert font_block["ascent"] > 0
    assert font_block["descent"] > 0
    assert len(font_block["glyphs"]) == 95
    assert "A" in font_block["glyphs"]
    assert font_block["glyphs"]["A"]["advance"] > 0


def test_index_ts_has_font_helpers(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    ts = (out / "index.ts").read_text()
    assert "glyphFrame" in ts
    assert "textSprites" in ts
    assert "FontBlock" in ts

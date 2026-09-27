"""Runtime tint, palette and lint-budget tests (Fase 1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sprout import palettes
from sprout.cli import _diff_specs, _generate, _lint_warnings, app
from sprout.exporter import render_items
from sprout.spec import SpecError, load_spec

SPECS = Path(__file__).resolve().parents[1] / "specs"
runner = CliRunner()


def _write(tmp_path, spec: dict) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "s.json"
    p.write_text(json.dumps(spec))
    return p


def _base(items: list[dict] | None = None, **extra) -> dict:
    spec = {
        "name": "tinted",
        "seed": 7,
        "layout": {"framePx": 32, "cols": 4, "tileLogical": 16},
        "items": items or [{"id": "rock", "generator": "props",
                            "frames": 2, "params": {"kind": "rock"}}],
    }
    spec.update(extra)
    return spec


# ── spec schema: colors + tint ───────────────────────────────────────────

def test_colors_normalized_and_tint_modes(tmp_path) -> None:
    spec = _base(
        items=[{"id": "rock", "generator": "props", "frames": 1,
                "params": {"kind": "rock"}, "tint": "shade"}],
        colors=[{"key": "ember", "hex": "#e4572e"}, {"key": "ink", "hex": "#abc"}],
    )
    s = load_spec(_write(tmp_path, spec))
    assert [(c.key, c.hex) for c in s.colors] == [("ember", "#E4572E"), ("ink", "#AABBCC")]
    assert s.items[0].tint == "shade"


def test_item_tint_defaults_to_none(tmp_path) -> None:
    s = load_spec(_write(tmp_path, _base()))
    assert s.items[0].tint == "none"
    assert s.colors == []


def test_invalid_tint_mode_rejected(tmp_path) -> None:
    spec = _base(items=[{"id": "a", "generator": "props", "frames": 1,
                         "params": {"kind": "rock"}, "tint": "glow"}])
    with pytest.raises(SpecError, match="tint"):
        load_spec(_write(tmp_path, spec))


@pytest.mark.parametrize("bad_hex", ["#GGHHII", "#12345", "red", 42])
def test_invalid_hex_rejected(tmp_path, bad_hex) -> None:
    spec = _base(colors=[{"key": "x", "hex": bad_hex}])
    with pytest.raises(SpecError, match="hex"):
        load_spec(_write(tmp_path, spec))


def test_duplicate_color_key_rejected(tmp_path) -> None:
    spec = _base(colors=[{"key": "x", "hex": "#112233"}, {"key": "x", "hex": "#445566"}])
    with pytest.raises(SpecError, match="duplicate color key"):
        load_spec(_write(tmp_path, spec))


def test_color_entry_requires_key_and_hex(tmp_path) -> None:
    spec = _base(colors=[{"key": "x"}])
    with pytest.raises(SpecError, match="'hex'"):
        load_spec(_write(tmp_path, spec))


# ── palettes ─────────────────────────────────────────────────────────────

def test_palette_fills_missing_colors(tmp_path) -> None:
    spec = _base(items=[{"id": "rock", "generator": "props", "frames": 1,
                         "params": {"kind": "rock", "palette": "earth"}}])
    s = load_spec(_write(tmp_path, spec))
    p = s.items[0].params
    assert p["fill"] == palettes.PALETTES["earth"]["fill"]
    assert p["outline"] == palettes.PALETTES["earth"]["outline"]
    assert p["accent"] == palettes.PALETTES["earth"]["accent"]


def test_palette_never_overrides_explicit_fill(tmp_path) -> None:
    spec = _base(items=[{"id": "rock", "generator": "props", "frames": 1,
                         "params": {"kind": "rock", "palette": "earth",
                                    "fill": [1, 2, 3]}}])
    s = load_spec(_write(tmp_path, spec))
    assert s.items[0].params["fill"] == [1, 2, 3]


def test_unknown_palette_rejected(tmp_path) -> None:
    spec = _base(items=[{"id": "rock", "generator": "props", "frames": 1,
                         "params": {"kind": "rock", "palette": "neon"}}])
    with pytest.raises(SpecError, match="unknown palette"):
        load_spec(_write(tmp_path, spec))


def test_outline_rule_helpers() -> None:
    assert palettes.darken((100, 200, 50)) == (55, 110, 28)
    assert palettes.outline_color((0, 0, 0)) == (0, 0, 0)
    assert palettes.outline_width(64) == 2
    assert palettes.outline_width(48) == 1
    assert palettes.outline_width(32) == 1


# ── manifest + index.ts contract ─────────────────────────────────────────

def _gen(tmp_path) -> tuple[dict, str]:
    out = tmp_path / "out"
    _generate(SPECS / "tint.json", out, None, False)
    manifest = json.loads((out / "manifest.json").read_text())
    return manifest, (out / "index.ts").read_text()


def test_manifest_has_tint_block(tmp_path) -> None:
    manifest, _ = _gen(tmp_path)
    tint = manifest["tint"]
    assert tint["colors"] == [
        {"key": "ember", "hex": "#E4572E"},
        {"key": "azure", "hex": "#3E8FD0"},
        {"key": "moss", "hex": "#5E984E"},
    ]
    assert tint["items"] == {"hero": "shade"}


def test_manifest_has_no_tint_block_by_default(tmp_path) -> None:
    out = tmp_path / "out"
    _generate(SPECS / "props.json", out, None, False)
    manifest = json.loads((out / "manifest.json").read_text())
    assert "tint" not in manifest


def test_index_ts_tint_helpers_present(tmp_path) -> None:
    _, src = _gen(tmp_path)
    for contract in (
        "export type TintMode = 'shade' | 'full';",
        "export const TINTS:",
        "export const TINT_MODES:",
        "export function tintModeFor(",
        "export function hexToRgb(",
        "export function colorMatrixFor(",
        "export const SILHOUETTE_MATRIX",
        "export function tintPaint(",
        "export function silhouettePaint(",
        "export function tintColor(",
        "export function tintColors(",
        "export function silhouetteColors(",
        "tint?: TintBlock;",
        "Skia.ColorFilter.MakeMatrix(",
        "0.2126", "0.7152", "0.0722",  # Rec.709 luminance (shade mode)
        "colorBlendMode=\"modulate\"",  # documented usage of tintColors
    ):
        assert contract in src, contract


def test_index_ts_tint_block_emitted_for_specs_without_tint(tmp_path) -> None:
    """Stable API surface: helpers exist even without a tint block."""
    out = tmp_path / "out"
    _generate(SPECS / "props.json", out, None, False)
    src = (out / "index.ts").read_text()
    assert "export function colorMatrixFor(" in src
    assert "manifest.tint?.colors ?? []" in src


def test_tint_generation_is_deterministic(tmp_path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    _generate(SPECS / "tint.json", a, None, False)
    _generate(SPECS / "tint.json", b, None, False)
    assert (a / "index.ts").read_bytes() == (b / "index.ts").read_bytes()
    assert (a / "manifest.json").read_bytes() == (b / "manifest.json").read_bytes()


# ── diff: tint and colors are part of the contract ──────────────────────

def _spec_dict(**overrides) -> dict:
    base = {
        "name": "d", "seed": 1, "layout": {"framePx": 32, "cols": 4},
        "items": [{"id": "rock", "generator": "props", "frames": 1,
                   "params": {"kind": "rock"}}],
    }
    base.update(overrides)
    return base


def test_diff_detects_tint_change(tmp_path) -> None:
    a = load_spec(_write(tmp_path / "a", _spec_dict()))
    b = load_spec(_write(tmp_path / "b", _spec_dict(items=[
        {"id": "rock", "generator": "props", "frames": 1,
         "params": {"kind": "rock"}, "tint": "shade"}])))
    assert any(d["field"] == "items.rock" for d in _diff_specs(a, b))


def test_diff_detects_colors_change(tmp_path) -> None:
    a = load_spec(_write(tmp_path / "a", _spec_dict()))
    b = load_spec(_write(tmp_path / "b", _spec_dict(
        colors=[{"key": "ember", "hex": "#E4572E"}])))
    assert any(d["field"] == "colors" for d in _diff_specs(a, b))


# ── lint: atlas size budget ──────────────────────────────────────────────

def test_lint_flags_atlas_over_budget(tmp_path) -> None:
    spec = tmp_path / "big.json"
    spec.write_text(json.dumps(_base(
        items=[{"id": "hero", "generator": "blob_walk", "frames": 8}],
        layout={"framePx": 64, "cols": 4, "tileLogical": 32},
    )))
    result = runner.invoke(app, ["lint", "--json", "--max-atlas-mb", "0.01", str(spec)])
    assert result.exit_code == 1, result.output
    data = json.loads(result.stdout)
    assert any(w["check"] == "atlas_size" for w in data["warnings"])


def test_lint_budget_can_be_disabled(tmp_path) -> None:
    spec = tmp_path / "big.json"
    spec.write_text(json.dumps(_base(
        items=[{"id": "hero", "generator": "blob_walk", "frames": 8}],
        layout={"framePx": 64, "cols": 4, "tileLogical": 32},
    )))
    result = runner.invoke(app, ["lint", "--json", "--max-atlas-mb", "0", str(spec)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert not any(w["check"] == "atlas_size" for w in data["warnings"])


def test_lint_default_budget_has_no_false_positive() -> None:
    """Every shipped spec stays under the default 16 MB budget."""
    for name in ("demo", "props", "tint", "ui", "particles", "font", "autotile", "runtime", "starter"):
        p = SPECS / f"{name}.json"
        if not p.is_file():
            continue
        spec = load_spec(p)
        warnings = _lint_warnings(spec, render_items(spec))
        assert not any(w["check"] == "atlas_size" for w in warnings), name

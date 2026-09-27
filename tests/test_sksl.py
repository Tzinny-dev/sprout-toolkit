"""Tests for the SkSL emitter (opt-in runtime mode)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from sprout import sksl
from sprout.cli import _generate
from sprout.exporter import build_shader, build_tier_shaders
from sprout.spec import SpecError, load_spec

SPEC = Path(__file__).resolve().parents[1] / "specs" / "runtime.json"
DEMO = Path(__file__).resolve().parents[1] / "specs" / "demo.json"


def _write(tmp_path, spec: dict) -> Path:
    p = tmp_path / "s.json"
    p.write_text(json.dumps(spec))
    return p


BASE = {
    "name": "rt", "seed": 5, "layout": {"cols": 4},
    "items": [{"id": "tiles", "generator": "terrain", "frames": 4}],
}


def test_runtime_off_by_default(tmp_path) -> None:
    s = load_spec(_write(tmp_path, dict(BASE)))
    assert s.runtime is None
    src, block = build_shader(s)
    assert src is None and block is None


def test_runtime_true_uses_defaults(tmp_path) -> None:
    s = load_spec(_write(tmp_path, {**BASE, "runtime": True}))
    assert s.runtime is not None
    src, block = build_shader(s)
    assert src is not None and "fbm" in src
    assert block["uniforms"]["octaves"] == 4
    assert block["uniforms"]["seed"] == 5


def test_runtime_params_and_seed_in_uniforms(tmp_path) -> None:
    spec = {**BASE, "seed": 42,
            "runtime": {"freq": 0.1, "octaves": 2, "tileable": True}}
    s = load_spec(_write(tmp_path, spec))
    _, block = build_shader(s)
    u = block["uniforms"]
    assert u == {
        "freq": 0.1, "octaves": 2, "seed": 42, "tileable": True,
        "tileWidth": 64, "tileHeight": 64, "period": 6,
        "time": 0.0,
        "base": [0.16, 0.27, 0.16], "accent": [0.90, 0.79, 0.46],
    }


@pytest.mark.parametrize("runtime", [
    {"freq": 0}, {"freq": -1}, {"octaves": 0}, {"octaves": 9},
    {"base": [2, 0, 0]}, {"wat": 1}, "si",
])
def test_runtime_invalid_rejected(tmp_path, runtime) -> None:
    with pytest.raises(SpecError, match="runtime"):
        load_spec(_write(tmp_path, {**BASE, "runtime": runtime}))


def test_generate_emits_sksl_manifest_and_ts(tmp_path: Path) -> None:
    out = tmp_path / "out"
    r = _generate(SPEC, out, None, False)
    assert r["skipped"] is False
    sksl = (out / "demo_runtime.sksl").read_text()
    assert "uniform float u_freq" in sksl and "half4 main" in sksl
    m = json.loads((out / "manifest.json").read_text())
    assert m["shader"]["file"] == "demo_runtime.sksl"
    assert m["shader"]["uniforms"]["seed"] == 1337
    src = (out / "index.ts").read_text()
    assert "export const SHADER_SKS" in src
    assert "export function shaderUniforms" in src
    assert "SHADER_DEFAULTS" in src


def test_generate_without_runtime_has_null_shader_exports(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(DEMO, out, None, False)
    assert not (out / "demo_atlas.sksl").exists()
    m = json.loads((out / "manifest.json").read_text())
    assert "shader" not in m
    src = (out / "index.ts").read_text()
    assert "SHADER_SKS: string | null = null" in src


def test_sksl_deterministic_and_seed_sensitive(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    _generate(SPEC, a, None, False)
    _generate(SPEC, b, None, False)
    _generate(SPEC, c, 9999, False)
    assert (a / "demo_runtime.sksl").read_bytes() == (b / "demo_runtime.sksl").read_bytes()
    ua = json.loads((a / "manifest.json").read_text())["shader"]["uniforms"]
    ub = json.loads((b / "manifest.json").read_text())["shader"]["uniforms"]
    uc = json.loads((c / "manifest.json").read_text())["shader"]["uniforms"]
    assert ua == ub
    assert ua["seed"] == 1337 and uc["seed"] == 9999


def test_skip_existing_covers_shader(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert _generate(SPEC, out, None, False)["skipped"] is False
    assert _generate(SPEC, out, None, True)["skipped"] is True
    # touching the .sksl file forces regeneration
    (out / "demo_runtime.sksl").write_text("// touched\n")
    assert _generate(SPEC, out, None, True)["skipped"] is False


# ── Tier effect templates (Fase 7) ─────────────────────────────────────
TIER_SPEC = {
    "name": "tt", "seed": 7, "layout": {"cols": 4},
    "items": [{"id": "coin", "generator": "props", "frames": 2,
               "params": {"kind": "treasure", "form": "coin"}}],
    "tiers": {
        "holo": "holographic",
        "boost": {"template": "neon", "speed": 2.0, "glow": 0.8},
        "legend": {"template": "legend-glow"},
        "off": "invisible",
    },
}


def test_normalize_tiers_shorthand_and_defaults() -> None:
    tiers = sksl.normalize_tiers(TIER_SPEC["tiers"])
    assert tiers is not None
    assert tiers["holo"] == {"template": "holographic",
                             "params": {"speed": 0.35, "glow": 0.5}}
    assert tiers["boost"]["params"] == {"speed": 2.0, "glow": 0.8}
    assert tiers["off"] == {"template": "invisible", "params": {}}


def test_normalize_tiers_none_when_absent() -> None:
    assert sksl.normalize_tiers(None) is None
    assert sksl.normalize_tiers(False) is None


@pytest.mark.parametrize("tiers", [
    {},
    {"x": "sparkle"},
    {"x": {"template": "neon", "wat": 1}},
    {"x": {"template": "neon", "speed": -1}},
    {"x": {"template": "neon", "glow": 2}},
    {"bad name!": "neon"},
    {"x": 42},
])
def test_normalize_tiers_invalid_rejected(tiers) -> None:
    with pytest.raises(ValueError, match="tiers"):
        sksl.normalize_tiers(tiers)


def test_load_spec_rejects_invalid_tiers(tmp_path) -> None:
    spec = {**TIER_SPEC, "tiers": {"x": "sparkle"}}
    with pytest.raises(SpecError, match="tiers"):
        load_spec(_write(tmp_path, spec))


@pytest.mark.parametrize("template", sksl.TIER_TEMPLATES)
def test_tier_template_renders_declared_uniforms(template: str) -> None:
    src = sksl.render_tier_shader(template)
    assert "half4 main" in src
    assert f"tier template: {template}" in src
    declared = set(re.findall(r"uniform float (u_\w+);", src))
    referenced = set(re.findall(r"\b(u_\w+)\b", src)) - declared
    # every uniform the body reads must be declared (u_seed/u_time always)
    assert referenced <= declared, f"{template}: undeclared {referenced}"
    assert {"u_seed", "u_time"} <= declared


@pytest.mark.parametrize("template", sksl.TIER_TEMPLATES)
def test_tier_template_ts_safe(template: str) -> None:
    """Sources are embedded in index.ts template literals: no ` or ${."""
    src = sksl.render_tier_shader(template)
    assert "`" not in src
    assert "${" not in src


def test_tier_shader_uniforms_derive_from_seed() -> None:
    u = sksl.tier_shader(42, "neon", {"speed": 2.0, "glow": 0.8})
    assert u == {"seed": 42, "time": 0.0, "speed": 2.0, "glow": 0.8}
    assert sksl.tier_shader(2**31 + 9, "neon", {})["seed"] == 9


def test_generate_emits_tier_sksl_manifest_and_ts(tmp_path: Path) -> None:
    p = _write(tmp_path, dict(TIER_SPEC))
    out = tmp_path / "out"
    _generate(p, out, None, False)
    for tier, file in (("holo", "tt.holo.sksl"), ("boost", "tt.boost.sksl"),
                       ("legend", "tt.legend.sksl"), ("off", "tt.off.sksl")):
        assert (out / file).is_file(), tier
    m = json.loads((out / "manifest.json").read_text())
    assert set(m["tiers"]) == {"holo", "boost", "legend", "off"}
    assert m["tiers"]["holo"]["template"] == "holographic"
    assert m["tiers"]["holo"]["file"] == "tt.holo.sksl"
    assert m["tiers"]["boost"]["uniforms"]["speed"] == 2.0
    src = (out / "index.ts").read_text()
    assert "export const TIER_SHADERS" in src
    assert "export function tierUniforms" in src
    assert "tier template: holographic" in src
    assert "manifest.tiers?.[name]?.uniforms" in src


def test_tier_sources_deterministic_and_seed_sensitive(tmp_path: Path) -> None:
    p = _write(tmp_path, dict(TIER_SPEC))
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    _generate(p, a, None, False)
    _generate(p, b, None, False)
    _generate(p, c, 999, False)
    assert (a / "tt.holo.sksl").read_bytes() == (b / "tt.holo.sksl").read_bytes()
    ua = json.loads((a / "manifest.json").read_text())["tiers"]["holo"]["uniforms"]
    uc = json.loads((c / "manifest.json").read_text())["tiers"]["holo"]["uniforms"]
    assert ua["seed"] == 7 and uc["seed"] == 999
    assert ua != uc


def test_skip_existing_covers_tier_sksl(tmp_path: Path) -> None:
    p = _write(tmp_path, dict(TIER_SPEC))
    out = tmp_path / "out"
    assert _generate(p, out, None, False)["skipped"] is False
    assert _generate(p, out, None, True)["skipped"] is True
    (out / "tt.boost.sksl").unlink()
    assert _generate(p, out, None, True)["skipped"] is False
    assert (out / "tt.boost.sksl").is_file()


def test_specs_without_tiers_emit_empty_map(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(DEMO, out, None, False)
    m = json.loads((out / "manifest.json").read_text())
    assert "tiers" not in m
    src = (out / "index.ts").read_text()
    assert "TIER_SHADERS: Record<string, string> = {}" in src


def test_build_tier_shaders_shape(tmp_path) -> None:
    s = load_spec(_write(tmp_path, dict(TIER_SPEC)))
    built = build_tier_shaders(s)
    assert set(built) == {"holo", "boost", "legend", "off"}
    assert built["off"]["template"] == "invisible"
    assert "half4 main" in built["legend"]["source"]

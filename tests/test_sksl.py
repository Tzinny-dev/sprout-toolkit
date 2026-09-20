"""Tests for the SkSL emitter (opt-in runtime mode)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sprout.cli import _generate
from sprout.exporter import build_shader
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

"""Tests del contrato CLI: comandos registrados, info y modo watch."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import zlib
from pathlib import Path
from typing import Callable

from PIL import Image
from typer.testing import CliRunner

from sprout.cli import app, _lint_warnings
from sprout.generators.base import FrameData
from sprout.spec import load_spec

SPECS = Path(__file__).resolve().parents[1] / "specs"
runner = CliRunner()


def _commands() -> set[str]:
    return {c.name or c.callback.__name__ for c in app.registered_commands}


def _crc(p: Path) -> int:
    return zlib.crc32(p.read_bytes()) & 0xFFFFFFFF


def _wait(pred: Callable[[], bool], timeout: float, what: str) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return
        time.sleep(0.1)
    raise AssertionError(f"timeout esperando: {what}")


def test_commands_registered() -> None:
    assert {"generate", "batch", "validate", "watch", "info", "lint"} <= _commands()


def test_watch_regenerates_on_spec_change(tmp_path: Path) -> None:
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    spec = spec_dir / "p.json"
    spec.write_text((SPECS / "props.json").read_text())
    out = tmp_path / "out"
    atlas = out / "atlas.png"

    proc = subprocess.Popen(
        [sys.executable, "-m", "sprout.cli", "watch", str(spec_dir),
         "--out", str(out), "--interval", "0.2"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        _wait(lambda: atlas.is_file(), 20, "generación inicial del watch")
        crc1 = _crc(atlas)

        raw = json.loads(spec.read_text())
        raw["seed"] = int(raw["seed"]) + 1
        spec.write_text(json.dumps(raw))

        _wait(lambda: atlas.is_file() and _crc(atlas) != crc1, 20,
              "regeneración tras cambio de seed")
        assert _crc(atlas) != crc1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_watch_skips_unchanged_spec(tmp_path: Path) -> None:
    """Tocar la spec sin cambiar su contenido -> skip (crc idéntico)."""
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    spec = spec_dir / "p.json"
    spec.write_text((SPECS / "props.json").read_text())
    out = tmp_path / "out"
    atlas = out / "atlas.png"

    proc = subprocess.Popen(
        [sys.executable, "-m", "sprout.cli", "watch", str(spec_dir),
         "--out", str(out), "--interval", "0.2"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        _wait(lambda: atlas.is_file(), 20, "generación inicial")
        crc1 = _crc(atlas)
        spec.touch()  # cambia mtime, no contenido
        time.sleep(1.5)
        assert _crc(atlas) == crc1  # el atlas no cambia
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


# ── Comando `info` ──────────────────────────────────────────────────────
def test_info_json_matches_spec() -> None:
    result = runner.invoke(app, ["info", "--json", str(SPECS / "demo.json")])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["name"] == "demo_atlas"
    assert data["seed"] == 1337
    assert data["layout"]["cols"] == 4 and data["layout"]["framePx"] == 64
    assert data["atlas"]["frames"] == 16
    assert data["atlas"]["width"] == 256 and data["atlas"]["height"] == 256
    assert [it["id"] for it in data["items"]] == ["hero", "tiles"]
    assert data["animations"]["walk"]["fps"] == 8
    assert data["runtime"] is False


def test_info_human_readable() -> None:
    result = runner.invoke(app, ["info", str(SPECS / "particles.json")])
    assert result.exit_code == 0, result.output
    out = result.stdout
    assert "particles_atlas" in out
    assert "seed    : 31337" in out
    assert "512x256" in out
    assert "particles" in out
    assert "burst_spark" in out


def test_info_invalid_spec_exits_1(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"name": "x"}')  # falta seed/items
    result = runner.invoke(app, ["info", str(bad)])
    assert result.exit_code == 1


def test_info_missing_file_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(app, ["info", str(tmp_path / "nope.json")])
    assert result.exit_code == 1


# ── Comando `lint` ───────────────────────────────────────────────────────
def test_lint_clean_spec_exits_zero() -> None:
    result = runner.invoke(app, ["lint", str(SPECS / "ui.json")])
    assert result.exit_code == 0, result.output
    assert "OK" in result.stdout


def test_lint_json_output() -> None:
    result = runner.invoke(app, ["lint", "--json", str(SPECS / "ui.json")])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["warnings"] == []


def test_lint_detects_padding(tmp_path: Path) -> None:
    spec = tmp_path / "padded.json"
    spec.write_text(json.dumps({
        "name": "padded_atlas",
        "seed": 1,
        "layout": {"framePx": 32, "cols": 10, "tileLogical": 16},
        "items": [
            {"id": "spark", "generator": "particles", "frames": 2,
             "params": {"kind": "spark", "particles": 4}},
        ],
    }))
    result = runner.invoke(app, ["lint", "--json", str(spec)])
    assert result.exit_code == 1, result.output
    data = json.loads(result.stdout)
    checks = {w["check"] for w in data["warnings"]}
    assert "padding" in checks


def test_lint_invalid_spec_exits_1(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"name": "x"}')  # falta seed/items
    result = runner.invoke(app, ["lint", str(bad)])
    assert result.exit_code == 1


def test_lint_warnings_flags_empty_frames() -> None:
    """Unitario: `_lint_warnings` detecta frames totalmente transparentes
    sin depender de que algún generador real produzca uno vacío."""
    spec = load_spec(SPECS / "ui.json")
    empty = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    items_frames = [[FrameData(id="ghost_00", image=empty)]]
    warnings = _lint_warnings(spec, items_frames)
    empty_warning = next(w for w in warnings if w["check"] == "empty_frames")
    assert empty_warning["ids"] == ["ghost_00"]


def test_lint_ignores_rgb_frames_without_alpha() -> None:
    """Los tiles RGB (terrain sin autotile) no tienen canal alpha: no deben
    dispararse como falso positivo de `empty_frames`."""
    spec = load_spec(SPECS / "ui.json")
    rgb_frame = Image.new("RGB", (64, 64), (10, 10, 10))
    items_frames = [[FrameData(id="tile_00", image=rgb_frame)]]
    warnings = _lint_warnings(spec, items_frames)
    assert not any(w["check"] == "empty_frames" for w in warnings)


def test_lint_terrain_spec_no_false_positive() -> None:
    """`demo.json` mezcla frames RGBA (hero) y RGB (tiles): no debe fallar
    ni marcar falsos positivos de frames vacíos."""
    result = runner.invoke(app, ["lint", "--json", str(SPECS / "demo.json")])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert not any(w["check"] == "empty_frames" for w in data["warnings"])

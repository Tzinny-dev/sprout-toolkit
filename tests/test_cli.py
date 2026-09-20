"""Tests for the CLI contract: registered commands, info, and watch mode."""
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

from sprout.cli import app, _generate, _lint_warnings
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
    raise AssertionError(f"timeout waiting for: {what}")


def test_commands_registered() -> None:
    assert {"generate", "batch", "validate", "watch", "info", "lint", "diff", "init"} <= _commands()


def test_init_writes_spec_and_generates(tmp_path: Path) -> None:
    """`sprout init` writes starter.json + atlas/manifest/index.ts; rerun keeps edits."""
    out = tmp_path / "starter"
    r = runner.invoke(app, ["init", "--out", str(out)])
    assert r.exit_code == 0, r.output
    spec = out / "starter.json"
    assert spec.is_file()
    for artifact in ("atlas.png", "manifest.json", "index.ts"):
        assert (out / artifact).is_file(), artifact
    assert _crc(out / "atlas.png") == 0xC4CAF76D  # starter seed=7 determinism pin

    edited = json.loads(spec.read_text())
    edited["seed"] = 999
    spec.write_text(json.dumps(edited))
    r2 = runner.invoke(app, ["init", "--out", str(out)])
    assert r2.exit_code == 0, r2.output
    assert "keep existing" in r2.output
    assert json.loads(spec.read_text())["seed"] == 999


def test_init_no_generate_flag(tmp_path: Path) -> None:
    out = tmp_path / "starter"
    r = runner.invoke(app, ["init", "--out", str(out), "--no-generate"])
    assert r.exit_code == 0, r.output
    assert (out / "starter.json").is_file()
    assert not (out / "atlas.png").exists()


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
        _wait(lambda: atlas.is_file(), 20, "initial watch generation")
        crc1 = _crc(atlas)

        raw = json.loads(spec.read_text())
        raw["seed"] = int(raw["seed"]) + 1
        spec.write_text(json.dumps(raw))

        _wait(lambda: atlas.is_file() and _crc(atlas) != crc1, 20,
              "regeneration after seed change")
        assert _crc(atlas) != crc1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_watch_skips_unchanged_spec(tmp_path: Path) -> None:
    """Touching the spec without changing its content -> skip (identical crc)."""
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
        _wait(lambda: atlas.is_file(), 20, "initial generation")
        crc1 = _crc(atlas)
        assert crc1 != 0, "atlas must be fully written before the test proceeds"
        spec.touch()  # changes mtime, not content
        time.sleep(1.5)
        assert _crc(atlas) == crc1  # the atlas doesn't change
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


# ── `info` command ───────────────────────────────────────────────────────
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
    bad.write_text('{"name": "x"}')  # missing seed/items
    result = runner.invoke(app, ["info", str(bad)])
    assert result.exit_code == 1


def test_info_missing_file_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(app, ["info", str(tmp_path / "nope.json")])
    assert result.exit_code == 1


# ── `lint` command ───────────────────────────────────────────────────────
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
    bad.write_text('{"name": "x"}')  # missing seed/items
    result = runner.invoke(app, ["lint", str(bad)])
    assert result.exit_code == 1


def test_lint_warnings_flags_empty_frames() -> None:
    """Unit test: `_lint_warnings` detects fully transparent frames without
    depending on some real generator producing an empty one."""
    spec = load_spec(SPECS / "ui.json")  # 3 items: btn, slider, panel
    empty = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    items_frames = [[], [], [FrameData(id="ghost_00", image=empty)]]
    warnings = _lint_warnings(spec, items_frames)
    empty_warning = next(w for w in warnings if w["check"] == "empty_frames")
    assert empty_warning["ids"] == ["ghost_00"]


def test_lint_ignores_rgb_frames_without_alpha() -> None:
    """RGB tiles (terrain without autotile) have no alpha channel: they must
    not trigger a false positive for `empty_frames`."""
    spec = load_spec(SPECS / "ui.json")  # 3 items: btn, slider, panel
    rgb_frame = Image.new("RGB", (64, 64), (10, 10, 10))
    items_frames = [[], [], [FrameData(id="tile_00", image=rgb_frame)]]
    warnings = _lint_warnings(spec, items_frames)
    assert not any(w["check"] == "empty_frames" for w in warnings)


def test_lint_terrain_spec_no_false_positive() -> None:
    """`demo.json` mixes RGBA frames (hero) and RGB frames (tiles): it must
    not fail or flag false positives for empty frames."""
    result = runner.invoke(app, ["lint", "--json", str(SPECS / "demo.json")])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert not any(w["check"] == "empty_frames" for w in data["warnings"])


def test_lint_font_spec_ignores_blank_space_glyph() -> None:
    """The space in `font.json` is intentionally an empty frame: `lint`
    must not flag it as `empty_frames`."""
    result = runner.invoke(app, ["lint", "--json", str(SPECS / "font.json")])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert not any(w["check"] == "empty_frames" for w in data["warnings"])


# ── `diff` command ───────────────────────────────────────────────────────
def _write_spec(path: Path, **overrides) -> None:
    base = {
        "name": "diff_atlas",
        "seed": 1,
        "files": {"atlas": "atlas.png"},
        "layout": {"framePx": 32, "cols": 4, "tileLogical": 16},
        "items": [
            {"id": "rock", "generator": "props", "frames": 2, "params": {"kind": "rock"}},
        ],
    }
    base.update(overrides)
    path.write_text(json.dumps(base))


def test_diff_specs_identical(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _write_spec(a)
    _write_spec(b)
    result = runner.invoke(app, ["diff", str(a), str(b)])
    assert result.exit_code == 0, result.output
    assert "no differences" in result.stdout


def test_diff_specs_detects_changes(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _write_spec(a, seed=1)
    _write_spec(b, seed=2, layout={"framePx": 32, "cols": 8, "tileLogical": 16})
    result = runner.invoke(app, ["diff", "--json", str(a), str(b)])
    assert result.exit_code == 1, result.output
    data = json.loads(result.stdout)
    fields = {d["field"] for d in data["diffs"]}
    assert "seed" in fields
    assert "layout.cols" in fields


def test_diff_specs_added_removed_items(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _write_spec(a)
    _write_spec(b, items=[
        {"id": "rock", "generator": "props", "frames": 2, "params": {"kind": "rock"}},
        {"id": "bush", "generator": "props", "frames": 3, "params": {"kind": "bush"}},
    ])
    result = runner.invoke(app, ["diff", "--json", str(a), str(b)])
    assert result.exit_code == 1, result.output
    data = json.loads(result.stdout)
    added = next(d for d in data["diffs"] if d["field"] == "items.bush")
    assert added["a"] is None and added["b"] == "added"


def test_diff_outputs_identical(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    _write_spec(spec)
    out_a, out_b = tmp_path / "a", tmp_path / "b"
    _generate(spec, out_a, None, False)
    _generate(spec, out_b, None, False)
    result = runner.invoke(app, ["diff", str(out_a), str(out_b)])
    assert result.exit_code == 0, result.output
    assert "no differences" in result.stdout


def test_diff_outputs_detects_seed_change(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    _write_spec(spec)
    out_a, out_b = tmp_path / "a", tmp_path / "b"
    _generate(spec, out_a, 1, False)
    _generate(spec, out_b, 2, False)
    result = runner.invoke(app, ["diff", "--json", str(out_a), str(out_b)])
    assert result.exit_code == 1, result.output
    data = json.loads(result.stdout)
    fields = {d["field"] for d in data["diffs"]}
    assert "atlas.crc" in fields


def test_diff_mismatched_types_exits_1(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    _write_spec(spec)
    result = runner.invoke(app, ["diff", str(spec), str(tmp_path)])
    assert result.exit_code == 1


def test_diff_json_output_shape(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _write_spec(a)
    _write_spec(b)
    result = runner.invoke(app, ["diff", "--json", str(a), str(b)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["kind"] == "spec"
    assert data["diffs"] == []


# ── Export: --png-mode / --texturepacker / --mipmaps ─────────────────────
def test_generate_png_mode_png8(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    _write_spec(spec)
    out = tmp_path / "out"
    result = runner.invoke(app, ["generate", str(spec), "--out", str(out), "--png-mode", "png8"])
    assert result.exit_code == 0, result.output
    with Image.open(out / "atlas.png") as img:
        assert img.mode == "P"


def test_generate_png_mode_png24(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    _write_spec(spec)
    out = tmp_path / "out"
    result = runner.invoke(app, ["generate", str(spec), "--out", str(out), "--png-mode", "png24"])
    assert result.exit_code == 0, result.output
    with Image.open(out / "atlas.png") as img:
        assert img.mode == "RGB"


def test_generate_invalid_png_mode_exits_1(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    _write_spec(spec)
    result = runner.invoke(app, ["generate", str(spec), "--png-mode", "webp"])
    assert result.exit_code == 1


def test_generate_texturepacker_writes_tpsheet(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    _write_spec(spec)
    out = tmp_path / "out"
    result = runner.invoke(app, ["generate", str(spec), "--out", str(out), "--texturepacker"])
    assert result.exit_code == 0, result.output
    tp = json.loads((out / "diff_atlas.tpsheet.json").read_text())
    assert set(tp["frames"]) == {"rock_00.png", "rock_01.png"}
    assert tp["meta"]["format"] == "RGBA8888"


def test_generate_mipmaps_writes_levels(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    _write_spec(spec)
    out = tmp_path / "out"
    result = runner.invoke(app, ["generate", str(spec), "--out", str(out), "--mipmaps"])
    assert result.exit_code == 0, result.output
    m = json.loads((out / "manifest.json").read_text())
    levels = m["mipmaps"]["levels"]
    assert len(levels) == 3
    for lvl in levels:
        assert (out / lvl["file"]).is_file()


def test_generate_mipmaps_custom_level_count(tmp_path: Path) -> None:
    spec = tmp_path / "spec.json"
    _write_spec(spec)
    out = tmp_path / "out"
    result = runner.invoke(
        app, ["generate", str(spec), "--out", str(out), "--mipmaps", "--mipmap-levels", "1"]
    )
    assert result.exit_code == 0, result.output
    m = json.loads((out / "manifest.json").read_text())
    assert len(m["mipmaps"]["levels"]) == 1


def test_skip_existing_still_generates_missing_texturepacker(tmp_path: Path) -> None:
    """`skip_existing` must not prevent an optional artifact from being
    emitted if it didn't exist yet from a previous run."""
    spec = tmp_path / "spec.json"
    _write_spec(spec)
    out = tmp_path / "out"
    _generate(spec, out, None, False)  # first run without --texturepacker
    tp_path = out / "diff_atlas.tpsheet.json"
    assert not tp_path.is_file()

    result = runner.invoke(
        app, ["generate", str(spec), "--out", str(out), "--skip-existing", "--texturepacker"]
    )
    assert result.exit_code == 0, result.output
    assert tp_path.is_file()


def test_skip_existing_works_with_non_default_png_mode(tmp_path: Path) -> None:
    """The CRC probe used by `skip_existing` must respect `--png-mode`,
    otherwise "no changes" detection would be broken for png8/png24."""
    spec = tmp_path / "spec.json"
    _write_spec(spec)
    out = tmp_path / "out"
    r1 = runner.invoke(
        app, ["generate", str(spec), "--out", str(out), "--png-mode", "png8", "--skip-existing"]
    )
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(
        app, ["generate", str(spec), "--out", str(out), "--png-mode", "png8", "--skip-existing"]
    )
    assert r2.exit_code == 0, r2.output
    assert "skip" in r2.stdout

"""Fase 6: multi-escala (tiers), --frame-px y siluetas prehechas."""
from __future__ import annotations

import json
import re
import zlib
from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from sprout.cli import app

SPEC = Path(__file__).resolve().parents[1] / "specs" / "demo.json"
runner = CliRunner()


def _plain(output: str) -> str:
    """Strip ANSI SGR codes — typer/rich highlight flag names with colors on
    (e.g. '-\\x1b[0m\\x1b[1;36m-tiers'), splitting '--tiers' across escapes."""
    return re.sub(r"\x1b\[[0-9;]*m", "", output)


def _crc(p: Path) -> int:
    return zlib.crc32(p.read_bytes()) & 0xFFFFFFFF


# ── --frame-px (sister outputs without editing the spec) ───────────────
def test_frame_px_override(tmp_path: Path) -> None:
    out = tmp_path / "out"
    r = runner.invoke(app, ["generate", str(SPEC), "-o", str(out),
                            "--frame-px", "96"])
    assert r.exit_code == 0, r.output
    m = json.loads((out / "manifest.json").read_text())
    assert m["units"]["framePx"] == 96
    assert m["files"]["atlasW"] == m["units"]["framePx"] * json.loads(
        SPEC.read_text())["layout"]["cols"]


def test_frame_px_invalid_exits_1(tmp_path: Path) -> None:
    r = runner.invoke(app, ["generate", str(SPEC), "-o", str(tmp_path),
                            "--frame-px", "4"])
    assert r.exit_code == 1
    assert "--frame-px" in _plain(r.output)


# ── --tiers (one atlas per resolution + combined index.ts) ─────────────
def test_tiers_generates_subdirs(tmp_path: Path) -> None:
    out = tmp_path / "tiers"
    r = runner.invoke(app, ["generate", str(SPEC), "-o", str(out),
                            "--tiers", "32,64"])
    assert r.exit_code == 0, r.output
    for px in (32, 64):
        assert (out / str(px) / "atlas.png").is_file()
        assert (out / str(px) / "manifest.json").is_file()
        assert (out / str(px) / "index.ts").is_file()
        m = json.loads((out / str(px) / "manifest.json").read_text())
        assert m["units"]["framePx"] == px
    assert not (out / "atlas.png").exists(), "tiers must not emit a root atlas"


def test_tiers_combined_index(tmp_path: Path) -> None:
    out = tmp_path / "tiers"
    runner.invoke(app, ["generate", str(SPEC), "-o", str(out),
                        "--tiers", "32,64,128"])
    src = (out / "index.ts").read_text()
    assert "export const atlasSources" in src
    assert "export function pickTier" in src
    assert "export type Tier = 32 | 64 | 128" in src
    assert "TIERS: readonly Tier[] = [32, 64, 128]" in src
    for px in (32, 64, 128):
        assert f"require('./{px}/atlas.png')" in src
    assert "import type { Manifest } from './32/index'" in src


def test_tiers_scales_atlas_size(tmp_path: Path) -> None:
    out = tmp_path / "tiers"
    runner.invoke(app, ["generate", str(SPEC), "-o", str(out),
                        "--tiers", "32,64"])
    w32 = json.loads((out / "32" / "manifest.json").read_text())["files"]["atlasW"]
    w64 = json.loads((out / "64" / "manifest.json").read_text())["files"]["atlasW"]
    assert w64 == w32 * 2


def test_tiers_deterministic(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    for dest in (a, b):
        runner.invoke(app, ["generate", str(SPEC), "-o", str(dest),
                            "--tiers", "32,64"])
    assert _crc(a / "64" / "atlas.png") == _crc(b / "64" / "atlas.png")
    assert (a / "index.ts").read_bytes() == (b / "index.ts").read_bytes()
    assert (a / "64" / "manifest.json").read_bytes() == \
        (b / "64" / "manifest.json").read_bytes()


def test_tiers_conflicts_with_frame_px(tmp_path: Path) -> None:
    r = runner.invoke(app, ["generate", str(SPEC), "-o", str(tmp_path),
                            "--tiers", "64", "--frame-px", "64"])
    assert r.exit_code == 1
    assert "mutually exclusive" in r.output


def test_invalid_tiers_value(tmp_path: Path) -> None:
    r = runner.invoke(app, ["generate", str(SPEC), "-o", str(tmp_path),
                            "--tiers", "abc"])
    assert r.exit_code != 0
    assert "--tiers" in _plain(r.output)


# ── --silhouette (prebaked black x alpha mask) ─────────────────────────
def test_silhouette_flag_emits_mask(tmp_path: Path) -> None:
    out = tmp_path / "out"
    r = runner.invoke(app, ["generate", str(SPEC), "-o", str(out),
                            "--silhouette"])
    assert r.exit_code == 0, r.output
    assert (out / "silhouette.png").is_file()
    m = json.loads((out / "manifest.json").read_text())
    assert m["files"]["silhouette"] == "silhouette.png"
    src = (out / "index.ts").read_text()
    assert "export const SILHOUETTE_SOURCE = require('./silhouette.png')" in src
    assert "useSilhouetteImage" in src


def test_silhouette_is_black_x_alpha(tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(app, ["generate", str(SPEC), "-o", str(out), "--silhouette"])
    atlas = Image.open(out / "atlas.png").convert("RGBA")
    sil = Image.open(out / "silhouette.png").convert("RGBA")
    assert sil.size == atlas.size
    # black x original alpha: same alpha, RGB forced to 0
    assert sil.getchannel("A").tobytes() == atlas.getchannel("A").tobytes()
    assert all(px[:3] == (0, 0, 0) for px in sil.getdata())


def test_without_silhouette_source_is_null(tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(app, ["generate", str(SPEC), "-o", str(out)])
    src = (out / "index.ts").read_text()
    assert "export const SILHOUETTE_SOURCE: number | null = null" in src
    assert "silhouette.png" not in src


def test_skip_existing_regenerates_deleted_silhouette(tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(app, ["generate", str(SPEC), "-o", str(out), "--silhouette"])
    (out / "silhouette.png").unlink()
    r = runner.invoke(app, ["generate", str(SPEC), "-o", str(out),
                            "--silhouette", "--skip-existing"])
    assert r.exit_code == 0
    assert (out / "silhouette.png").is_file()


def test_tiers_with_silhouette(tmp_path: Path) -> None:
    out = tmp_path / "tiers"
    r = runner.invoke(app, ["generate", str(SPEC), "-o", str(out),
                            "--tiers", "32,64", "--silhouette"])
    assert r.exit_code == 0, r.output
    for px in (32, 64):
        assert (out / str(px) / "silhouette.png").is_file()


# ── emitted runtime helpers ────────────────────────────────────────────
def test_index_exposes_layout_and_silhouette_helpers(tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(app, ["generate", str(SPEC), "-o", str(out)])
    src = (out / "index.ts").read_text()
    assert "export function spriteLayout(" in src
    assert "export function useSilhouetteSprites(" in src
    # centers by the frame's bounding box inside a size x size target
    assert "const box = Math.max(f.w, f.h);" in src
    assert "return { id, x: cx, y: cy, scale: size / box };" in src

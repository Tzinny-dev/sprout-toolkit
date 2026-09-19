"""Tests de determinismo y contrato de salida."""
from __future__ import annotations

import json
import zlib
from pathlib import Path

from imgi.cli import _generate

SPEC = Path(__file__).resolve().parents[1] / "specs" / "demo.json"


def _crc(p: Path) -> int:
    return zlib.crc32(p.read_bytes()) & 0xFFFFFFFF


def test_two_runs_byte_identical(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    _generate(SPEC, a, None, False)
    _generate(SPEC, b, None, False)
    assert _crc(a / "atlas.png") == _crc(b / "atlas.png")
    assert (a / "manifest.json").read_bytes() == (b / "manifest.json").read_bytes()
    assert (a / "index.ts").read_bytes() == (b / "index.ts").read_bytes()


def test_seed_override_changes_output(tmp_path: Path) -> None:
    ref = tmp_path / "ref"
    alt = tmp_path / "alt"
    _generate(SPEC, ref, None, False)
    _generate(SPEC, alt, 9999, False)
    assert _crc(ref / "atlas.png") != _crc(alt / "atlas.png")
    assert json.loads((alt / "manifest.json").read_text())["seed"] == 9999


def test_skip_existing_is_idempotent(tmp_path: Path) -> None:
    out = tmp_path / "out"
    r1 = _generate(SPEC, out, None, False)
    r2 = _generate(SPEC, out, None, True)
    assert r1["skipped"] is False
    assert r2["skipped"] is True
    assert r1["crc"] == r2["crc"]


def test_manifest_shape(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    m = json.loads((out / "manifest.json").read_text())
    assert m["schema"] == "imgi/manifest@0"
    assert len(m["frames"]) == 16
    assert m["anim"]["walk"]["frames"] == [f"hero_{i:02d}" for i in range(8)]
    assert set(m["tiles"]["ids"]) == {f"tiles_{i:02d}" for i in range(8)}
    assert m["units"] == {"tileLogical": 32, "framePx": 64, "sample": "nearest"}


def test_index_ts_references_atlas_and_types(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    src = (out / "index.ts").read_text()
    assert "require('./atlas.png')" in src
    assert "export const manifest: Manifest = require('./manifest.json')" in src
    assert "export function framesFor" in src
    assert "FilterMode.Nearest" in src
    # helpers de worklets/buffers (§8.2)
    assert "export function rectFor" in src
    assert "export const frameScale" in src
    assert "export const atlasSampling" in src
    assert "export function useAtlasImage" in src
    assert "export function useAtlasSprites" in src
    assert "export function useAtlasGrid" in src
    assert "useRectBuffer" in src and "useRSXformBuffer" in src
    assert "{ filter: sampleMode }" in src
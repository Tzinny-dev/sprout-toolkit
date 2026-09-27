"""Tests for `sprout import <dir>` — loose PNGs -> atlas + manifest + index.ts."""
from __future__ import annotations

import json
import zlib
from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from sprout.cli import app

runner = CliRunner()


def _crc(p: Path) -> int:
    return zlib.crc32(p.read_bytes()) & 0xFFFFFFFF


def _make_frames(tmp_path: Path, count: int = 3, size: tuple[int, int] = (64, 64)) -> Path:
    d = tmp_path / "frames"
    d.mkdir()
    for i in range(count):
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        img.putpixel((i, i), (255, 128, 0, 255))
        img.putpixel((size[0] // 2, size[1] // 2), (10, 20, 30, 255))
        img.save(d / f"wave_{i}.png")
    (d / "notes.txt").write_text("ignored")
    return d


def test_import_packs_frames(tmp_path: Path) -> None:
    src = _make_frames(tmp_path)
    out = tmp_path / "out"
    r = runner.invoke(app, ["import", str(src), "-o", str(out), "--cols", "2"])
    assert r.exit_code == 0, r.output
    assert (out / "atlas.png").is_file()
    assert (out / "manifest.json").is_file()
    assert (out / "index.ts").is_file()
    m = json.loads((out / "manifest.json").read_text())
    assert [f["id"] for f in m["frames"]] == ["wave_0", "wave_1", "wave_2"]
    assert m["schemaVersion"] == 1
    assert m["units"] == {"tileLogical": 64, "framePx": 64, "sample": "nearest"}
    atlas = Image.open(out / "atlas.png")
    assert atlas.size == (128, 128)  # cols=2, three 64px frames -> 2x2 grid
    src_index = (out / "index.ts").read_text()
    # ids live in manifest.json (required at runtime), not inlined in the module
    assert "frameById" in src_index and "manifest.json" in src_index


def test_import_ids_sorted_by_filename(tmp_path: Path) -> None:
    src = _make_frames(tmp_path, count=2)
    (src / "alpha.png").write_bytes((src / "wave_0.png").read_bytes())
    out = tmp_path / "out"
    runner.invoke(app, ["import", str(src), "-o", str(out)])
    m = json.loads((out / "manifest.json").read_text())
    assert [f["id"] for f in m["frames"]] == ["alpha", "wave_0", "wave_1"]


def test_import_deterministic(tmp_path: Path) -> None:
    src = _make_frames(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    for dest in (a, b):
        r = runner.invoke(app, ["import", str(src), "-o", str(dest)])
        assert r.exit_code == 0, r.output
    assert _crc(a / "atlas.png") == _crc(b / "atlas.png")
    assert (a / "manifest.json").read_bytes() == (b / "manifest.json").read_bytes()


def test_import_rejects_mixed_sizes(tmp_path: Path) -> None:
    src = _make_frames(tmp_path)
    big = Image.new("RGBA", (32, 32), (1, 2, 3, 255))
    big.save(src / "tiny.png")
    r = runner.invoke(app, ["import", str(src), "-o", str(tmp_path / "out")])
    assert r.exit_code == 1
    assert "64x64" in r.output and "32x32" in r.output


def test_import_rejects_empty_dir(tmp_path: Path) -> None:
    src = tmp_path / "empty"
    src.mkdir()
    r = runner.invoke(app, ["import", str(src), "-o", str(tmp_path / "out")])
    assert r.exit_code == 1
    assert "no *.png" in r.output


def test_import_rejects_bad_id(tmp_path: Path) -> None:
    src = _make_frames(tmp_path, count=1)
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 255))
    img.save(src / "bad name.png")
    r = runner.invoke(app, ["import", str(src), "-o", str(tmp_path / "out")])
    assert r.exit_code == 1
    assert "bad name" in r.output


def test_import_rejects_unreadable_png(tmp_path: Path) -> None:
    src = _make_frames(tmp_path, count=1)
    (src / "broken.png").write_bytes(b"not a png")
    r = runner.invoke(app, ["import", str(src), "-o", str(tmp_path / "out")])
    assert r.exit_code == 1
    assert "broken.png" in r.output


def test_import_requires_directory(tmp_path: Path) -> None:
    r = runner.invoke(app, ["import", str(tmp_path / "nope"),
                            "-o", str(tmp_path / "out")])
    assert r.exit_code == 1
    assert "not a directory" in r.output

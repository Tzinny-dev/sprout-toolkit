"""Tests for `exporter.py`: PNG modes, TexturePacker and atlas mipmaps."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from sprout.exporter import (
    apply_png_mode,
    build_sheet,
    build_texturepacker,
    compute_mipmap_meta,
    write_mipmap_files,
)
from sprout.generators.base import FrameData
from sprout.spec import load_spec

SPECS = Path(__file__).resolve().parents[1] / "specs"


def _sample_atlas(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([4, 4, size - 20, size - 20], fill=(200, 50, 50, 255))
    d.ellipse([10, 10, size - 10, size - 10], fill=(50, 200, 50, 128))
    return img


# ── apply_png_mode ────────────────────────────────────────────────────────
def test_apply_png_mode_rgba_is_noop() -> None:
    img = _sample_atlas()
    out = apply_png_mode(img, "rgba")
    assert out.mode == "RGBA"
    assert out.tobytes() == img.tobytes()


def test_apply_png_mode_png24_drops_alpha() -> None:
    img = _sample_atlas()
    out = apply_png_mode(img, "png24")
    assert out.mode == "RGB"


def test_apply_png_mode_png8_preserves_alpha() -> None:
    img = _sample_atlas()
    out = apply_png_mode(img, "png8")
    assert out.mode == "P"
    roundtrip = out.convert("RGBA")
    assert roundtrip.getpixel((0, 0))[3] == 0           # corner: transparent
    assert roundtrip.getpixel((24, 10))[3] == 255       # red circle only: opaque
    assert roundtrip.getpixel((28, 28))[3] == 128       # overlap: semi-transparent


# ── build_texturepacker ───────────────────────────────────────────────────
def test_build_texturepacker_shape() -> None:
    sheet = _sample_atlas(128)
    records = [
        {"id": "rock_00", "col": 0, "row": 0, "x": 0, "y": 0, "w": 64, "h": 64},
        {"id": "rock_01", "col": 1, "row": 0, "x": 64, "y": 0, "w": 64, "h": 64},
    ]
    spec = load_spec(SPECS / "props.json")
    tp = build_texturepacker(spec, records, "atlas.png", sheet, "rgba")

    assert set(tp["frames"]) == {"rock_00.png", "rock_01.png"}
    frame = tp["frames"]["rock_01.png"]
    assert frame["frame"] == {"x": 64, "y": 0, "w": 64, "h": 64}
    assert frame["sourceSize"] == {"w": 64, "h": 64}
    assert tp["meta"]["image"] == "atlas.png"
    assert tp["meta"]["size"] == {"w": 128, "h": 128}
    assert tp["meta"]["format"] == "RGBA8888"


def test_build_texturepacker_format_matches_png_mode() -> None:
    sheet = _sample_atlas(64)
    spec = load_spec(SPECS / "props.json")
    tp = build_texturepacker(spec, [], "atlas.png", sheet, "png8")
    assert tp["meta"]["format"] == "I8"


# ── compute_mipmap_meta ────────────────────────────────────────────────────
def test_compute_mipmap_meta_halves_dimensions() -> None:
    sheet = _sample_atlas(256)
    spec = load_spec(SPECS / "props.json")
    meta = compute_mipmap_meta(sheet, spec, levels=3)
    assert [lvl["scale"] for lvl in meta] == [0.5, 0.25, 0.125]
    assert [lvl["w"] for lvl in meta] == [128, 64, 32]
    assert [lvl["h"] for lvl in meta] == [128, 64, 32]
    assert meta[0]["file"].endswith("@0.5x.png")


def test_compute_mipmap_meta_stops_before_min_size() -> None:
    sheet = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    spec = load_spec(SPECS / "props.json")
    meta = compute_mipmap_meta(sheet, spec, levels=5)
    # 16 -> 8 -> 4 -> (2, discarded for being < 4px)
    assert [lvl["w"] for lvl in meta] == [8, 4]


# ── write_mipmap_files ─────────────────────────────────────────────────────
def test_write_mipmap_files_creates_expected_pngs(tmp_path: Path) -> None:
    sheet = _sample_atlas(128)
    spec = load_spec(SPECS / "props.json")
    meta = compute_mipmap_meta(sheet, spec, levels=2)
    write_mipmap_files(sheet, tmp_path, "rgba", meta)

    for lvl in meta:
        p = tmp_path / lvl["file"]
        assert p.is_file()
        with Image.open(p) as img:
            assert img.size == (lvl["w"], lvl["h"])


# ── build_sheet: opt-in anchor per frame ───────────────────────────────────
def test_build_sheet_includes_anchor_when_present() -> None:
    spec = load_spec(SPECS / "props.json")
    img = Image.new("RGBA", (spec.layout.frame_px, spec.layout.frame_px), (0, 0, 0, 0))
    frames_with_anchor = [FrameData(id="rock_00", image=img, meta={"anchor": {"x": 10, "y": 20}})]
    _, records = build_sheet(spec, [frames_with_anchor])
    assert records[0]["anchor"] == {"x": 10, "y": 20}


def test_build_sheet_omits_anchor_when_absent() -> None:
    spec = load_spec(SPECS / "props.json")
    img = Image.new("RGBA", (spec.layout.frame_px, spec.layout.frame_px), (0, 0, 0, 0))
    frames_without_anchor = [FrameData(id="spark_00", image=img)]
    _, records = build_sheet(spec, [frames_without_anchor])
    assert "anchor" not in records[0]

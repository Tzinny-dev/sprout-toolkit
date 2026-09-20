"""Tests del generador `ui` (botones, sliders, paneles 9-patch)."""
from __future__ import annotations

import json
import zlib
from pathlib import Path

import pytest

from sprout.cli import _generate
from sprout.generators import GENERATORS
from sprout.generators.ui import Ui

SPEC = Path(__file__).resolve().parents[1] / "specs" / "ui.json"


def _crc(p: Path) -> int:
    return zlib.crc32(p.read_bytes()) & 0xFFFFFFFF


def _opaque(img) -> bool:
    return img.getchannel("A").getbbox() is not None


# ── Contrato del plug-in ────────────────────────────────────────────────
def test_registered() -> None:
    assert Ui.id == "ui"
    assert GENERATORS["ui"] is Ui


def test_button_renders_nonempty() -> None:
    frames = Ui().generate(seed=1, count=3, frame_px=64, params={"kind": "button"})
    assert len(frames) == 3
    for fr in frames:
        assert fr.image.size == (64, 64)
        assert fr.image.mode == "RGBA"
        assert _opaque(fr.image)


def test_slider_renders_nonempty() -> None:
    frames = Ui().generate(seed=1, count=6, frame_px=64, params={"kind": "slider"})
    assert len(frames) == 6
    for fr in frames:
        assert _opaque(fr.image)


def test_panel_renders_nonempty() -> None:
    frames = Ui().generate(seed=1, count=9, frame_px=64, params={"kind": "panel"})
    assert len(frames) == 9
    for fr in frames:
        assert fr.image.size == (64, 64)
        assert _opaque(fr.image)


def test_default_kind_is_button() -> None:
    frames = Ui().generate(1, 3, 64, {})
    assert _opaque(frames[0].image)


def test_invalid_kind_raises() -> None:
    with pytest.raises(ValueError, match="kind"):
        Ui().generate(1, 1, 64, {"kind": "dragon"})


def test_panel_requires_9_frames() -> None:
    with pytest.raises(ValueError, match="9"):
        Ui().generate(1, 8, 64, {"kind": "panel"})
    with pytest.raises(ValueError, match="9"):
        Ui().generate(1, 10, 64, {"kind": "panel"})


# ── Determinismo ────────────────────────────────────────────────────────
def test_same_seed_is_byte_identical() -> None:
    a = Ui().generate(42, 3, 64, {"kind": "button"})
    b = Ui().generate(42, 3, 64, {"kind": "button"})
    assert [f.image.tobytes() for f in a] == [f.image.tobytes() for f in b]

    a = Ui().generate(42, 6, 64, {"kind": "slider"})
    b = Ui().generate(42, 6, 64, {"kind": "slider"})
    assert [f.image.tobytes() for f in a] == [f.image.tobytes() for f in b]


def test_panel_deterministic_regardless_of_seed() -> None:
    """El panel no usa variación por seed: es una construcción geométrica fija."""
    a = Ui().generate(1, 9, 64, {"kind": "panel"})
    b = Ui().generate(999, 9, 64, {"kind": "panel"})
    assert [f.image.tobytes() for f in a] == [f.image.tobytes() for f in b]


# ── Contenido específico por kind ────────────────────────────────────────
def test_button_states_differ() -> None:
    """normal/hover/pressed deben producir bytes distintos entre sí."""
    frames = Ui().generate(7, 3, 64, {"kind": "button"})
    assert len({f.image.tobytes() for f in frames}) == 3


def test_slider_frames_differ() -> None:
    """El knob debe desplazarse: cada paso de progreso es distinto."""
    frames = Ui().generate(7, 6, 64, {"kind": "slider"})
    assert len({f.image.tobytes() for f in frames}) == 6


def test_panel_patches_all_distinct() -> None:
    """Esquinas/bordes/centro deben ser 9 tiles visualmente distintas."""
    frames = Ui().generate(1, 9, 64, {"kind": "panel"})
    assert len({f.image.tobytes() for f in frames}) == 9


# ── Paleta ───────────────────────────────────────────────────────────────
def test_color_override_applied_button() -> None:
    frames = Ui().generate(
        1, 1, 64, {"kind": "button", "fill": [10, 20, 30], "outline": [1, 2, 3]}
    )
    colors = {px[:3] for px in frames[0].image.getdata() if px[3] > 0}
    assert (10, 20, 30) in colors
    assert (1, 2, 3) in colors


def test_color_override_applied_slider_accent() -> None:
    frames = Ui().generate(
        1, 2, 64, {"kind": "slider", "accent": [5, 6, 7]}
    )
    colors = {px[:3] for px in frames[1].image.getdata() if px[3] > 0}
    assert (5, 6, 7) in colors


def test_size_scales_with_frame_px() -> None:
    for size in (32, 64, 128):
        frames = Ui().generate(3, 1, size, {"kind": "button"})
        assert frames[0].image.size == (size, size)
        frames = Ui().generate(3, 9, size, {"kind": "panel"})
        assert frames[0].image.size == (size, size)


# ── Pipeline completo (spec -> atlas + manifest + index.ts) ─────────────
def test_spec_generates_all_outputs(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    assert (out / "atlas.png").is_file()
    assert (out / "manifest.json").is_file()
    assert (out / "index.ts").is_file()


def test_spec_deterministic(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    _generate(SPEC, a, None, False)
    _generate(SPEC, b, None, False)
    assert _crc(a / "atlas.png") == _crc(b / "atlas.png")
    assert (a / "manifest.json").read_bytes() == (b / "manifest.json").read_bytes()


def test_manifest_frames_and_shape(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _generate(SPEC, out, None, False)
    m = json.loads((out / "manifest.json").read_text())
    # 3 btn + 6 slider + 9 panel = 18
    assert len(m["frames"]) == 18
    ids = {f["id"] for f in m["frames"]}
    assert "btn_00" in ids and "btn_02" in ids
    assert "panel_08" in ids
    assert m["schema"] == "sprout/manifest@0"

"""Tests for form-coverage measurement (`sprout diversity`)."""
from __future__ import annotations

import json

import pytest
from PIL import Image
from typer.testing import CliRunner

from sprout import diversity
from sprout.exporter import FrameData
from sprout.cli import app
from sprout.spec import Item

runner = CliRunner()


def _img(alpha: int, size: int = 32) -> Image.Image:
    return Image.new("RGBA", (size, size), (0, 0, 0, alpha))


def _item(iid: str, generator: str = "props") -> Item:
    return Item(id=iid, generator=generator, frames=1, params={})


# ── form_signature ──────────────────────────────────────────────────────

def test_signature_is_deterministic():
    assert diversity.form_signature(_img(255)) == diversity.form_signature(_img(255))


def test_signature_depends_on_alpha_not_color():
    """Tint is a runtime dimension; the form is the silhouette."""
    red = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
    blue = Image.new("RGBA", (32, 32), (0, 0, 255, 255))
    assert diversity.form_signature(red) == diversity.form_signature(blue)


def test_signature_differs_for_different_silhouettes():
    solid = _img(255)
    hollow = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    hollow.paste((0, 0, 0, 255), (8, 8, 24, 24))
    assert diversity.form_signature(solid) != diversity.form_signature(hollow)


def test_signature_handles_non_rgba_images():
    """terrain emits images without an alpha channel."""
    rgb = Image.new("RGB", (32, 32), (120, 120, 120))
    assert len(diversity.form_signature(rgb)) == diversity.FORM_GRID ** 2


def test_signature_length_is_grid_squared():
    assert len(diversity.form_signature(_img(255))) == 256


# ── hamming ─────────────────────────────────────────────────────────────

def test_hamming_is_zero_for_identical():
    assert diversity.hamming(b"\x00" * 256, b"\x00" * 256) == 0


def test_hamming_counts_differing_bits():
    assert diversity.hamming(b"\x00", b"\xff") == 8


def test_hamming_is_symmetric():
    a, b = b"\x0f" * 256, b"\xf0" * 256
    assert diversity.hamming(a, b) == diversity.hamming(b, a) == 2048


# ── diversity_groups ────────────────────────────────────────────────────

def _frames(alpha: int) -> list[FrameData]:
    return [FrameData(id="", image=_img(alpha))]


def test_no_collisions_when_all_forms_differ():
    items = [_item("a"), _item("b"), _item("c")]
    frames = [_frames(255), _frames(128), _frames(0)]
    assert diversity.diversity_groups(items, frames) == []


def test_collision_groups_items_with_same_form():
    items = [_item("a"), _item("b"), _item("c")]
    frames = [_frames(255), _frames(255), _frames(0)]
    assert diversity.diversity_groups(items, frames) == [["a", "b"]]


def test_collision_reports_all_members():
    items = [_item(x) for x in "abcde"]
    frames = [_frames(255)] * 4 + [_frames(0)]
    assert diversity.diversity_groups(items, frames) == [["a", "b", "c", "d"]]


def test_empty_frames_are_skipped():
    items = [_item("a"), _item("b")]
    frames = [[], _frames(255)]
    assert diversity.diversity_groups(items, frames) == []


def test_distinct_forms_counts_renderable_items():
    assert diversity.distinct_forms([_frames(1), _frames(2), []]) == 2


def test_distinct_forms_empty():
    assert diversity.distinct_forms([]) == 0


# ── CLI ─────────────────────────────────────────────────────────────────

def _write_spec(tmp_path, items: list[dict]) -> str:
    p = tmp_path / "s.json"
    p.write_text(json.dumps({
        "name": "x", "seed": 1, "layout": {"cols": 4}, "items": items,
    }))
    return str(p)


def test_cli_reports_no_collisions(tmp_path):
    spec = _write_spec(tmp_path, [
        {"id": "hero", "generator": "blob_walk", "frames": 8},
        {"id": "tiles", "generator": "terrain", "frames": 8},
    ])
    r = runner.invoke(app,
                      ["diversity", spec])
    assert r.exit_code == 0
    assert "no collisions" in r.output


def test_cli_reports_collisions_and_fails(tmp_path):
    """Two props items with the same form+seed-slot render identically."""
    spec = _write_spec(tmp_path, [
        {"id": "cookie", "generator": "props", "frames": 1,
         "params": {"kind": "sweet", "form": "cookie"}},
        {"id": "coin", "generator": "props", "frames": 1,
         "params": {"kind": "sweet", "form": "cookie"}},
    ])
    r = runner.invoke(app,
                      ["diversity", spec])
    assert r.exit_code == 1
    assert "collision" in r.output
    assert "cookie" in r.output and "coin" in r.output


def test_cli_no_fail_flag_exits_zero(tmp_path):
    spec = _write_spec(tmp_path, [
        {"id": "cookie", "generator": "props", "frames": 1,
         "params": {"kind": "sweet", "form": "cookie"}},
        {"id": "coin", "generator": "props", "frames": 1,
         "params": {"kind": "sweet", "form": "cookie"}},
    ])
    r = runner.invoke(app,
                      ["diversity", spec, "--no-fail"])
    assert r.exit_code == 0


def test_cli_json_output(tmp_path):
    spec = _write_spec(tmp_path, [
        {"id": "hero", "generator": "blob_walk", "frames": 8},
    ])
    r = runner.invoke(app,
                      ["diversity", spec, "--json"])
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["items"] == 1
    assert data["collisions"] == []


def test_cli_invalid_spec_exits_one(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"name":"x","seed":1,"layout":{"cols":4},"items":['
                 '{"id":"a","generator":"nope","frames":1}]}')
    r = runner.invoke(app,
                      ["diversity", str(p)])
    assert r.exit_code == 1
    assert "invalid" in r.output


def test_cli_lists_colliding_ids(tmp_path):
    spec = _write_spec(tmp_path, [
        {"id": "cookie", "generator": "props", "frames": 1,
         "params": {"kind": "sweet", "form": "cookie"}},
        {"id": "coin", "generator": "props", "frames": 1,
         "params": {"kind": "sweet", "form": "cookie"}},
    ])
    r = runner.invoke(app,
                      ["diversity", spec])
    assert "cookie, coin" in r.output

"""Tests for form-coverage measurement (`sprout diversity`)."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from sprout import diversity
from sprout.cli import app
from sprout.spec import Item

runner = CliRunner()


def _item(iid: str, generator: str = "props", frames: int = 1,
          params: dict | None = None, autotile: int | None = None,
          tint: str = "none") -> Item:
    return Item(id=iid, generator=generator, frames=frames,
                params=params or {}, autotile=autotile, tint=tint)


# ── form_signature ──────────────────────────────────────────────────────

def test_signature_is_deterministic():
    a = _item("a", params={"kind": "sweet", "form": "cookie"})
    assert diversity.form_signature(a) == diversity.form_signature(a)


def test_signature_ignores_params_dict_order():
    a = _item("a", params={"kind": "sweet", "form": "cookie"})
    b = _item("b", params={"form": "cookie", "kind": "sweet"})
    assert diversity.form_signature(a) == diversity.form_signature(b)


def test_signature_differs_on_generator():
    a = _item("a", generator="props", params={"form": "cookie"})
    b = _item("b", generator="face", params={"form": "cookie"})
    assert diversity.form_signature(a) != diversity.form_signature(b)


def test_signature_differs_on_frames():
    """A 4-frame blink of happy is not the 1-frame still of happy."""
    a = _item("happy", frames=1, params={"mood": "happy"})
    b = _item("blink", frames=4, params={"mood": "happy"})
    assert diversity.form_signature(a) != diversity.form_signature(b)


def test_signature_differs_on_autotile():
    a = _item("a", autotile=47, params={"kind": "stone"})
    b = _item("b", params={"kind": "stone"})
    assert diversity.form_signature(a) != diversity.form_signature(b)


def test_signature_differs_on_structural_param():
    a = _item("a", params={"form": "cookie"})
    b = _item("b", params={"form": "donut"})
    assert diversity.form_signature(a) != diversity.form_signature(b)


def test_signature_ignores_missing_and_empty_params():
    assert (diversity.form_signature(_item("a"))
            == diversity.form_signature(_item("b")))


def test_signature_ignores_palette():
    """A palette is colours only — same form, repainted."""
    a = _item("a", params={"kind": "earth", "palette": "earth"})
    b = _item("b", params={"kind": "earth", "palette": "ocean"})
    assert diversity.form_signature(a) == diversity.form_signature(b)


def test_signature_ignores_color_literal_values():
    a = _item("a", params={"form": "gem", "fill": "#88ccff"})
    b = _item("b", params={"form": "gem", "fill": [0.5, 0.8, 1.0]})
    assert diversity.form_signature(a) == diversity.form_signature(b)


def test_signature_ignores_item_tint_field():
    """tint only declares runtime recolouring, it is not the form."""
    a = _item("a", tint="shade", params={"form": "gem"})
    b = _item("b", tint="full", params={"form": "gem"})
    assert diversity.form_signature(a) == diversity.form_signature(b)


def test_signature_keeps_non_color_lists():
    a = _item("a", params={"eyes": ["open", "shut", "wide"]})
    b = _item("b", params={"eyes": ["open", "shut"]})
    assert diversity.form_signature(a) != diversity.form_signature(b)


def test_signature_freezes_nested_values():
    """Nested params must stay hashable so signatures can be compared."""
    sig = diversity.form_signature(_item("a", params={"shape": {"r": 1}}))
    assert sig == diversity.form_signature(_item("b", params={"shape": {"r": 1}}))
    assert diversity.form_signature(_item("c", params={"shape": {"r": 2}})) != sig


# ── is_color ────────────────────────────────────────────────────────────

def test_is_color_hex_string():
    assert diversity.is_color("#a1b2c3")


def test_is_color_rgb_triple():
    assert diversity.is_color([1.0, 0.5, 0.0])
    assert diversity.is_color((255, 128, 0))


def test_is_color_rgba_quadruple():
    assert diversity.is_color([1.0, 0.5, 0.0, 0.5])


def test_is_not_color_scalars_and_names():
    assert not diversity.is_color("earth")
    assert not diversity.is_color(42)
    assert not diversity.is_color(True)
    assert not diversity.is_color(None)


def test_is_not_color_list_of_strings():
    assert not diversity.is_color(["open", "shut"])
    assert not diversity.is_color([True, False, True])


# ── diversity_groups ────────────────────────────────────────────────────

def test_no_collisions_when_all_forms_differ():
    items = [_item("a", params={"form": "cookie"}),
             _item("b", params={"form": "donut"}),
             _item("c", params={"form": "gem"})]
    assert diversity.diversity_groups(items) == []


def test_collision_groups_items_with_same_form():
    items = [_item("a", params={"form": "cookie"}),
             _item("b", params={"form": "cookie"}),
             _item("c", params={"form": "gem"})]
    assert diversity.diversity_groups(items) == [["a", "b"]]


def test_collision_reports_all_members():
    items = [_item(x, params={"form": "cookie"}) for x in "abcde"]
    assert diversity.diversity_groups(items) == [["a", "b", "c", "d", "e"]]


def test_groups_keep_spec_order():
    items = [_item("a", params={"form": "cookie"}),
             _item("b", params={"form": "gem"}),
             _item("c", params={"form": "cookie"}),
             _item("d", params={"form": "gem"})]
    assert diversity.diversity_groups(items) == [["a", "c"], ["b", "d"]]


def test_empty_items_have_no_groups():
    assert diversity.diversity_groups([]) == []


# ── distinct_forms ──────────────────────────────────────────────────────

def test_distinct_forms_counts_different_params():
    items = [_item("a", params={"form": "cookie"}),
             _item("b", params={"form": "donut"}),
             _item("c", params={"form": "cookie"})]
    assert diversity.distinct_forms(items) == 2


def test_distinct_forms_collapses_identical_items():
    items = [_item(x, params={"form": "cookie"}) for x in "abcd"]
    assert diversity.distinct_forms(items) == 1


def test_distinct_forms_empty():
    assert diversity.distinct_forms([]) == 0


def test_distinct_forms_matches_group_math():
    """distinct = items - members absorbed by each collision group."""
    items = [_item("a", params={"form": "cookie"}),
             _item("b", params={"form": "cookie"}),
             _item("c", params={"form": "gem"}),
             _item("d", params={"form": "gem"}),
             _item("e", params={"form": "gem"})]
    groups = diversity.diversity_groups(items)
    assert diversity.distinct_forms(items) == len(items) - sum(
        len(m) - 1 for m in groups)
    assert diversity.distinct_forms(items) == 2


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
    r = runner.invoke(app, ["diversity", spec])
    assert r.exit_code == 0
    assert "no collisions" in r.output


def test_cli_reports_collisions_and_fails(tmp_path):
    spec = _write_spec(tmp_path, [
        {"id": "cookie", "generator": "props", "frames": 1,
         "params": {"kind": "sweet", "form": "cookie"}},
        {"id": "coin", "generator": "props", "frames": 1,
         "params": {"kind": "sweet", "form": "cookie"}},
    ])
    r = runner.invoke(app, ["diversity", spec])
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
    r = runner.invoke(app, ["diversity", spec, "--no-fail"])
    assert r.exit_code == 0


def test_cli_json_output(tmp_path):
    spec = _write_spec(tmp_path, [
        {"id": "hero", "generator": "blob_walk", "frames": 8},
    ])
    r = runner.invoke(app, ["diversity", spec, "--json"])
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert data["items"] == 1
    assert data["distinct_forms"] == 1
    assert data["collisions"] == []


def test_cli_json_counts_collapsed_forms(tmp_path):
    spec = _write_spec(tmp_path, [
        {"id": "cookie", "generator": "props", "frames": 1,
         "params": {"form": "cookie"}},
        {"id": "coin", "generator": "props", "frames": 1,
         "params": {"form": "cookie"}},
    ])
    r = runner.invoke(app, ["diversity", spec, "--json", "--no-fail"])
    data = json.loads(r.output)
    assert data["items"] == 2
    assert data["distinct_forms"] == 1
    assert data["collisions"] == [{"items": ["cookie", "coin"]}]


def test_cli_same_form_different_palette_collides(tmp_path):
    """Dropping colours makes repainted copies of one form collide."""
    spec = _write_spec(tmp_path, [
        {"id": "a", "generator": "props", "frames": 1,
         "params": {"form": "gem", "palette": "earth"}},
        {"id": "b", "generator": "props", "frames": 1,
         "params": {"form": "gem", "palette": "ocean"}},
    ])
    r = runner.invoke(app, ["diversity", spec, "--no-fail"])
    assert r.exit_code == 0
    assert "1 distinct forms" in r.output
    assert "a, b" in r.output


def test_cli_invalid_spec_exits_one(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"name":"x","seed":1,"layout":{"cols":4},"items":['
                 '{"id":"a","generator":"nope","frames":1}]}')
    r = runner.invoke(app, ["diversity", str(p)])
    assert r.exit_code == 1
    assert "invalid" in r.output


def test_cli_lists_colliding_ids(tmp_path):
    spec = _write_spec(tmp_path, [
        {"id": "cookie", "generator": "props", "frames": 1,
         "params": {"kind": "sweet", "form": "cookie"}},
        {"id": "coin", "generator": "props", "frames": 1,
         "params": {"kind": "sweet", "form": "cookie"}},
    ])
    r = runner.invoke(app, ["diversity", spec])
    assert "cookie, coin" in r.output

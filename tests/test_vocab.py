"""Tests for data-driven vocabularies (sprout/vocab.py + assets/vocab/*.json)."""
from __future__ import annotations

import json

import pytest

from sprout import vocab
from sprout.generators.face import HEADS, MOODS, EYES
from sprout.generators.props import FORMS, FORM_COLORS


# ── Packaged vocabularies ───────────────────────────────────────────────

def test_props_forms_match_packaged_json():
    data = json.loads((vocab.ASSETS_DIR / "props.json").read_text())
    assert {k: list(v) for k, v in FORMS.items()} == data["forms"]


def test_props_colors_match_packaged_json():
    data = json.loads((vocab.ASSETS_DIR / "props.json").read_text())
    for kind, forms in data["colors"].items():
        for form, colors in forms.items():
            assert FORM_COLORS[kind][form] == {
                k: tuple(v) for k, v in colors.items()
            }


def test_face_moods_match_packaged_json():
    data = json.loads((vocab.ASSETS_DIR / "face.json").read_text())
    assert MOODS == data["moods"]


def test_face_part_vocabularies_match_packaged_json():
    data = json.loads((vocab.ASSETS_DIR / "face.json").read_text())
    assert list(HEADS) == data["heads"]
    assert list(EYES) == data["eyes"]


def test_load_returns_normalized_tuples():
    """Colors are [r,g,b] in JSON and (r,g,b) in the code."""
    data = vocab.load("props")
    assert data["colors"]["fruit"]["apple"]["fill"] == (214, 64, 70)


def test_load_returns_form_lists():
    data = vocab.load("props")
    assert isinstance(data["forms"]["fruit"], list)
    assert "apple" in data["forms"]["fruit"]


# ── Normalization ───────────────────────────────────────────────────────

def test_normalize_converts_three_int_lists_to_tuples():
    assert vocab._normalize([1, 2, 3]) == (1, 2, 3)


def test_normalize_leaves_other_lists_alone():
    assert vocab._normalize(["auto", "apple"]) == ["auto", "apple"]


def test_normalize_recurses_into_dicts():
    assert vocab._normalize({"a": [1, 2, 3], "b": {"c": [4, 5, 6]}}) == \
        {"a": (1, 2, 3), "b": {"c": (4, 5, 6)}}


def test_normalize_handles_nested_lists():
    assert vocab._normalize([[1, 2, 3], [4, 5, 6]]) == [(1, 2, 3), (4, 5, 6)]


# ── Deep merge ─────────────────────────────────────────────────────────

def test_deep_merge_replaces_lists():
    base = {"forms": {"fruit": ["auto", "apple"]}}
    override = {"forms": {"fruit": ["auto", "cherry"]}}
    assert vocab._deep_merge(base, override)["forms"]["fruit"] == \
        ["auto", "cherry"]


def test_deep_merge_merges_dicts_recursively():
    base = {"moods": {"happy": {"eyes": "open"}, "sad": {"eyes": "open"}}}
    override = {"moods": {"happy": {"mouth": "grin"}}}
    merged = vocab._deep_merge(base, override)
    assert merged["moods"]["happy"] == {"eyes": "open", "mouth": "grin"}
    assert merged["moods"]["sad"] == {"eyes": "open"}


def test_deep_merge_does_not_mutate_base():
    base = {"a": {"b": 1}}
    vocab._deep_merge(base, {"a": {"c": 2}})
    assert base == {"a": {"b": 1}}


# ── Override directory ──────────────────────────────────────────────────

def test_override_dir_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv(vocab.OVERRIDE_ENV, str(tmp_path))
    assert vocab.override_dir() == str(tmp_path)


def test_override_dir_none_when_unset(monkeypatch):
    monkeypatch.delenv(vocab.OVERRIDE_ENV, raising=False)
    assert vocab.override_dir() is None


def test_load_with_override_adds_new_form(monkeypatch, tmp_path):
    override = tmp_path / "props.json"
    override.write_text(json.dumps({
        "forms": {"fruit": ["auto", "apple", "cherry", "kiwi"]},
    }))
    monkeypatch.setenv(vocab.OVERRIDE_ENV, str(tmp_path))
    data = vocab.load("props")
    assert "kiwi" in data["forms"]["fruit"]
    assert "apple" in data["forms"]["fruit"]


def test_load_with_override_adds_new_kind(monkeypatch, tmp_path):
    override = tmp_path / "props.json"
    override.write_text(json.dumps({
        "forms": {"drink": ["auto", "soda", "juice"]},
    }))
    monkeypatch.setenv(vocab.OVERRIDE_ENV, str(tmp_path))
    data = vocab.load("props")
    assert "drink" in data["forms"]
    assert "fruit" in data["forms"]


def test_load_with_override_adds_new_mood(monkeypatch, tmp_path):
    override = tmp_path / "face.json"
    override.write_text(json.dumps({
        "moods": {"fierce": {"eyes": "angry", "mouth": "frown",
                            "brows": "angry", "extras": "anger"}},
    }))
    monkeypatch.setenv(vocab.OVERRIDE_ENV, str(tmp_path))
    data = vocab.load("face")
    assert "fierce" in data["moods"]
    assert "happy" in data["moods"]


def test_load_ignores_missing_override_file(monkeypatch, tmp_path):
    monkeypatch.setenv(vocab.OVERRIDE_ENV, str(tmp_path))
    data = vocab.load("props")
    assert "fruit" in data["forms"]


def test_load_ignores_override_for_other_vocab(monkeypatch, tmp_path):
    """A face.json override must not leak into props."""
    override = tmp_path / "face.json"
    override.write_text(json.dumps({"moods": {"fierce": {}}}))
    monkeypatch.setenv(vocab.OVERRIDE_ENV, str(tmp_path))
    data = vocab.load("props")
    assert "fruit" in data["forms"]


# ── Generator integration ───────────────────────────────────────────────

def test_props_uses_vocabulary_loader():
    from sprout.generators import props as props_mod
    assert props_mod.FORMS is not None
    assert "fruit" in props_mod.FORMS


def test_face_uses_vocabulary_loader():
    from sprout.generators import face as face_mod
    assert face_mod.MOODS is not None
    assert "happy" in face_mod.MOODS


def test_override_flows_into_generator(monkeypatch, tmp_path):
    """A consumer's new form becomes available to the generator."""
    override = tmp_path / "props.json"
    override.write_text(json.dumps({
        "forms": {"fruit": ["auto", "apple", "dragonfruit"]},
        "colors": {"fruit": {"dragonfruit": {"fill": [200, 50, 200],
                                               "accent": [100, 200, 100]}}},
    }))
    monkeypatch.setenv(vocab.OVERRIDE_ENV, str(tmp_path))

    import importlib
    import sprout.vocab as v
    importlib.reload(v)
    import sprout.generators.props as props_mod
    importlib.reload(props_mod)

    assert "dragonfruit" in props_mod.FORMS["fruit"]
    assert props_mod.FORM_COLORS["fruit"]["dragonfruit"]["fill"] == (200, 50, 200)


# ── What the vocabulary can and cannot do ───────────────────────────────

def test_face_new_mood_needs_no_renderer(monkeypatch, tmp_path):
    """Moods are part combinations, so a new one works immediately."""
    override = tmp_path / "face.json"
    override.write_text(json.dumps({
        "moods": {"fierce": {"eyes": "angry", "mouth": "frown",
                            "brows": "angry", "extras": "anger"}},
    }))
    monkeypatch.setenv(vocab.OVERRIDE_ENV, str(tmp_path))

    import importlib
    import sprout.vocab as v
    importlib.reload(v)
    import sprout.generators.face as face_mod
    importlib.reload(face_mod)

    assert "fierce" in face_mod.MOODS
    assert face_mod.MOODS["fierce"]["eyes"] == "angry"


def test_props_new_form_without_renderer_fails_loudly(monkeypatch, tmp_path):
    """A new props form needs a renderer method; the error says so."""
    override = tmp_path / "props.json"
    override.write_text(json.dumps({
        "forms": {"fruit": ["auto", "apple", "dragonfruit"]},
        "colors": {"fruit": {"dragonfruit": {"fill": [200, 50, 200],
                                               "accent": [100, 200, 100]}}},
    }))
    monkeypatch.setenv(vocab.OVERRIDE_ENV, str(tmp_path))

    import importlib
    import sprout.vocab as v
    importlib.reload(v)
    import sprout.generators.props as props_mod
    importlib.reload(props_mod)

    with pytest.raises(AttributeError, match="_dragonfruit"):
        props_mod.Props().generate(1, 1, 32, {"kind": "fruit",
                                              "form": "dragonfruit"})
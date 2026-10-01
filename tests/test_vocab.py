"""Tests for data-driven vocabularies (sprout/vocab.py + assets/vocab/*.json)."""
from __future__ import annotations

import contextlib
import importlib
import json
import sys

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


def test_critter_parts_match_packaged_json():
    from sprout.generators.critter import (
        ARCHETYPES, EARS, FACINGS, LEGS, PATTERNS, SNOUT, TAIL, WINGS,
    )
    data = json.loads((vocab.ASSETS_DIR / "critter.json").read_text())
    assert list(ARCHETYPES) == data["archetypes"]
    assert list(FACINGS) == data["facings"]
    assert list(EARS) == data["parts"]["ears"]
    assert list(SNOUT) == data["parts"]["snout"]
    assert list(TAIL) == data["parts"]["tail"]
    assert list(LEGS) == data["parts"]["legs"]
    assert list(WINGS) == data["parts"]["wings"]
    assert list(PATTERNS) == data["parts"]["pattern"]


def test_critter_auto_table_matches_packaged_json():
    """The per-archetype pick table travels with the word lists: an option
    only means something if some archetype can pick it."""
    from sprout.generators.critter import _AUTO
    data = json.loads((vocab.ASSETS_DIR / "critter.json").read_text())
    assert {a: {p: list(o) for p, o in parts.items()}
            for a, parts in _AUTO.items()} == data["auto"]


def test_flora_parts_match_packaged_json():
    from sprout.generators.flora import AGES, CANOPY, FORMS, KINDS, TRUNK
    data = json.loads((vocab.ASSETS_DIR / "flora.json").read_text())
    assert list(KINDS) == data["kinds"]
    assert list(CANOPY) == data["canopy"]
    assert list(TRUNK) == data["trunk"]
    assert list(AGES) == data["ages"]
    assert list(FORMS) == data["forms"]


def test_flora_age_mods_match_packaged_json():
    from sprout.generators.flora import _AGE_MODS
    data = json.loads((vocab.ASSETS_DIR / "flora.json").read_text())
    assert _AGE_MODS == data["age_mods"]


def test_flora_plant_forms_are_forms_without_auto():
    """Derived, so the seed's option list cannot drift from the vocabulary."""
    from sprout.generators.flora import FORMS, _PLANT_FORMS
    assert _PLANT_FORMS == tuple(f for f in FORMS if f != "auto")
    assert "auto" not in _PLANT_FORMS


@contextlib.contextmanager
def _vocab_override(tmp_path, monkeypatch, **files):
    """Point SPROUT_VOCAB_DIR at ``files`` and reload those generators,
    restoring the packaged defaults on the way out.

    ``importlib.reload`` mutates module globals for the rest of the session,
    so the exit path reloads again with the env var gone; without it a later
    test would silently inherit another test's vocabulary.
    """
    for name, data in files.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(data))
    monkeypatch.setenv(vocab.OVERRIDE_ENV, str(tmp_path))
    importlib.reload(sys.modules["sprout.vocab"])
    mods = {}
    for name in files:
        mod = importlib.import_module(f"sprout.generators.{name}")
        mods[name] = importlib.reload(mod)
    try:
        yield mods
    finally:
        monkeypatch.delenv(vocab.OVERRIDE_ENV, raising=False)
        importlib.reload(sys.modules["sprout.vocab"])
        for mod in mods.values():
            importlib.reload(mod)


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

def test_critter_override_flows_into_generator(monkeypatch, tmp_path):
    """A consumer's new ear option reaches both the word list and the table
    the seed picks from."""
    with _vocab_override(tmp_path, monkeypatch, critter={
        "parts": {"ears": ["auto", "none", "round", "pointy", "long", "tuft"]},
        "auto": {"quadruped": {"ears": ["round", "pointy", "tuft"]}},
    }) as mods:
        critter = mods["critter"]
        assert "tuft" in critter.EARS
        assert "tuft" in critter._AUTO["quadruped"]["ears"]


def test_flora_new_age_stage_needs_no_renderer(monkeypatch, tmp_path):
    """A stage is pure data — its numbers ride along with its name — so a new
    age draws on the spot, and draws something different from the default."""
    colossal = {"trunk_h": 1.30, "trunk_w": 1.80, "canopy_r": 1.50,
                "branches": 1.40, "n_lobes": 1.30, "lean": 1.20,
                "kink": 1.20, "fruit_p": 1.70}
    with _vocab_override(tmp_path, monkeypatch, flora={
        "ages": ["auto", "sapling", "young", "mature", "old", "colossal"],
        "age_mods": {"colossal": colossal},
    }) as mods:
        flora = mods["flora"]
        assert "colossal" in flora.AGES
        assert flora._AGE_MODS["colossal"] == colossal

        def px(params):
            return bytes(flora.Flora().generate(7, 1, 64, params)[0].image.tobytes())

        assert px({"kind": "tree", "age": "colossal"}) != px({"kind": "tree"})


def test_critter_unknown_option_draws_nothing_silently(monkeypatch, tmp_path):
    """Known gap, pinned so it stays visible.

    A vocabulary declares what a spec may *say*; it does not extend what the
    toolkit can *draw*. ``critter`` dispatches its parts through if/elif with
    no terminal else, so an option with no renderer branch is accepted and
    then paints nothing: ``tuft`` comes out pixel-identical to ``none``, with
    no error anywhere. ``props`` fails loudly here (AttributeError) because it
    dispatches through getattr. Documented in
    docs/generators.md#data-driven-vocabularies.
    """
    with _vocab_override(tmp_path, monkeypatch, critter={
        "parts": {"ears": ["auto", "none", "round", "pointy", "long", "tuft"]},
    }) as mods:
        critter = mods["critter"]

        def px(params):
            return bytes(critter.Critter().generate(7, 1, 64, params)[0].image.tobytes())

        base = {"archetype": "quadruped"}
        assert px({**base, "ears": "tuft"}) == px({**base, "ears": "none"})
        assert px({**base, "ears": "tuft"}) != px({**base, "ears": "round"})

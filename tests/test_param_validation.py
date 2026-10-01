"""Unknown-param validation: a typo in a mapping must fail loudly."""
from __future__ import annotations

import json

import pytest

from sprout.generators import GENERATORS
from sprout.generators.base import FRAMEWORK_PARAMS
from sprout.spec import SpecError, load_spec


def _write(tmp_path, generator: str, params: dict):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({
        "name": "x", "seed": 1, "layout": {"cols": 4},
        "items": [{"id": "a", "generator": generator, "frames": 1,
                   "params": params}],
    }))
    return p


# ── The typo case this feature exists for ──────────────────────────────

def test_typoed_param_is_rejected(tmp_path) -> None:
    p = _write(tmp_path, "props", {"kind": "fruit", "forma": "banana"})
    with pytest.raises(SpecError, match="unknown param"):
        load_spec(p)


def test_error_names_the_offending_key_and_the_known_ones(tmp_path) -> None:
    p = _write(tmp_path, "props", {"forma": "banana"})
    with pytest.raises(SpecError) as exc:
        load_spec(p)
    msg = str(exc.value)
    assert "'forma'" in msg
    assert "kind" in msg and "form" in msg


def test_error_reports_every_unknown_key(tmp_path) -> None:
    p = _write(tmp_path, "props", {"kindh": 1, "forma": 2, "accsent": 3})
    with pytest.raises(SpecError) as exc:
        load_spec(p)
    for bad in ("kindh", "forma", "accsent"):
        assert bad in str(exc.value)


def test_error_is_deterministic_in_key_order(tmp_path) -> None:
    p = _write(tmp_path, "props", {"z": 1, "a": 2})
    with pytest.raises(SpecError) as exc:
        load_spec(p)
    assert "'a', 'z'" in str(exc.value)


def test_error_mentions_the_item_id(tmp_path) -> None:
    p = _write(tmp_path, "ui", {"kynd": "button"})
    with pytest.raises(SpecError, match="'a'"):
        load_spec(p)


# ── Legitimate params keep working ─────────────────────────────────────

@pytest.mark.parametrize("generator", sorted(GENERATORS))
def test_every_builtin_generator_accepts_its_own_params(tmp_path, generator) -> None:
    """Each generator's declared surface must validate against itself."""
    declared = GENERATORS[generator].PARAMS
    params = {name: "auto" for name in declared}
    s = load_spec(_write(tmp_path, generator, params))
    assert s.items[0].params == params


def test_declared_surface_is_not_empty(tmp_path) -> None:
    for generator in GENERATORS:
        assert GENERATORS[generator].PARAMS


def test_params_are_preserved_not_rewritten(tmp_path) -> None:
    s = load_spec(_write(tmp_path, "critter", {"archetype": "bird", "facing": "left"}))
    assert s.items[0].params == {"archetype": "bird", "facing": "left"}


# ── Framework params are not generator params ──────────────────────────

def test_palette_is_accepted_everywhere(tmp_path) -> None:
    """`palette` is resolved by the framework before validation runs."""
    for generator in GENERATORS:
        load_spec(_write(tmp_path, generator, {"palette": "earth"}))


def test_palette_expansion_does_not_trip_validation(tmp_path) -> None:
    """resolve_params injects fill/accent/outline; those are real roles."""
    s = load_spec(_write(tmp_path, "props", {"palette": "earth"}))
    assert s.items[0].params["fill"] == [176, 124, 74]


def test_autotile_is_accepted_on_terrain(tmp_path) -> None:
    p = tmp_path / "s.json"
    p.write_text(json.dumps({
        "name": "x", "seed": 1, "layout": {"cols": 4},
        "items": [{"id": "t", "generator": "terrain", "frames": 16,
                   "autotile": 16}],
    }))
    assert load_spec(p).items[0].params["autotile"] == 16


def test_framework_params_are_the_documented_set() -> None:
    assert FRAMEWORK_PARAMS == {"palette", "autotile"}


def test_palette_on_a_colorless_generator_is_tolerated(tmp_path) -> None:
    """terrain has no color roles; resolve_params injects them anyway.

    The author's intent was `palette`, not three stray colors, so the
    injected keys must not be reported as unknown params.
    """
    s = load_spec(_write(tmp_path, "terrain", {"palette": "earth"}))
    assert s.items[0].params["fill"] == [176, 124, 74]


def test_framework_params_do_not_leak_into_generator_surfaces() -> None:
    """They are handled centrally, so no generator should redeclare them."""
    for generator, cls in GENERATORS.items():
        overlap = set(cls.PARAMS) & FRAMEWORK_PARAMS
        assert not overlap, f"{generator} redeclares {overlap}"


# ── Ordering: the palette error must still win ─────────────────────────

def test_unknown_palette_is_reported_before_unknown_params(tmp_path) -> None:
    p = _write(tmp_path, "props", {"palette": "neon", "zzz": 1})
    with pytest.raises(SpecError, match="unknown palette"):
        load_spec(p)
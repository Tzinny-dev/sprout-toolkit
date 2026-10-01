"""Tests for the plug-in registry: entry-point discovery + collisions."""
from __future__ import annotations

import pytest

from sprout import plugins
import sprout.generators as reg
from sprout.generators import (
    BUILTIN_GENERATORS,
    GENERATORS,
    Generator,
    get_generator,
    plugin_generator_ids,
)
from sprout.generators.base import FrameData
from sprout.spec import SpecError, load_spec


class Vehicle(Generator):
    id = "vehicle"
    PARAMS = frozenset({"wheels", "fill"})

    def generate(self, seed, count, frame_px, params, base=0):
        return [FrameData(id="", image=None) for _ in range(count)]


class Paramsless(Generator):
    """Third-party plug-in that predates the PARAMS surface."""

    id = "paramsless"

    def generate(self, seed, count, frame_px, params, base=0):
        return [FrameData(id="", image=None) for _ in range(count)]


class Nameless(Generator):
    id = ""

    def generate(self, seed, count, frame_px, params, base=0):
        return []


class NotAGenerator:
    """A plain object that is not a Generator at all."""





class FakeEntryPoint:
    """Stands in for importlib.metadata.EntryPoint."""

    def __init__(self, obj=None, error: Exception | None = None):
        self._obj = obj
        self._error = error

    def load(self):
        if self._error is not None:
            raise self._error
        return self._obj


@pytest.fixture
def fake_eps(monkeypatch):
    def _install(*eps: FakeEntryPoint):
        monkeypatch.setattr(plugins, "entry_points", lambda group: list(eps))
    return _install


def _spec(tmp_path, params: dict, generator: str = "props") -> Path:
    p = tmp_path / "spec.json"
    p.write_text(
        '{"name":"s","seed":1,"layout":{"cols":4},"items":['
        f'{{"id":"a","generator":"{generator}","frames":1,"params":{params}}}]}}'
    )
    return p


# ── Discovery ──────────────────────────────────────────────────────────

def test_discover_returns_declared_ids(fake_eps):
    fake_eps(FakeEntryPoint(Vehicle))
    assert plugins.discover() == {"vehicle": Vehicle}


def test_discover_accepts_instance_as_well_as_class(fake_eps):
    fake_eps(FakeEntryPoint(Vehicle()))
    assert plugins.discover()["vehicle"] is Vehicle


def test_first_duplicate_id_wins(fake_eps):
    class Other(Generator):
        id = "vehicle"

        def generate(self, seed, count, frame_px, params, base=0):
            return []

    fake_eps(FakeEntryPoint(Vehicle), FakeEntryPoint(Other))
    assert plugins.discover()["vehicle"] is Vehicle


# ── Failures are skipped, never raised ─────────────────────────────────

def test_import_error_is_skipped(fake_eps):
    fake_eps(FakeEntryPoint(error=RuntimeError("boom")), FakeEntryPoint(Vehicle))
    assert plugins.discover() == {"vehicle": Vehicle}


def test_non_generator_object_is_skipped(fake_eps):
    fake_eps(FakeEntryPoint(NotAGenerator), FakeEntryPoint(Vehicle))
    assert plugins.discover() == {"vehicle": Vehicle}


def test_generator_without_id_is_skipped(fake_eps):
    fake_eps(FakeEntryPoint(Nameless), FakeEntryPoint(Vehicle))
    assert plugins.discover() == {"vehicle": Vehicle}


def test_all_broken_plugins_yield_empty_registry(fake_eps):
    fake_eps(FakeEntryPoint(error=ValueError("x")), FakeEntryPoint(NotAGenerator))
    assert plugins.discover() == {}


# ── load_into: registration + collision policy ─────────────────────────

def test_load_into_adds_new_ids(monkeypatch):
    monkeypatch.setattr(plugins, "discover", lambda group: {})
    registry: dict = {}
    assert plugins.load_into(registry) == []
    assert registry == {}


def test_load_into_merges_without_touching_builtins(fake_eps, monkeypatch):
    fake_eps(FakeEntryPoint(Vehicle))
    monkeypatch.setattr(plugins, "discover", lambda group: {"vehicle": Vehicle})
    registry: dict = {}
    assert plugins.load_into(registry) == ["vehicle"]
    assert registry["vehicle"] is Vehicle


def test_builtin_id_is_never_shadowed(fake_eps, monkeypatch):
    """A plug-in claiming 'props' must not replace the built-in."""
    class Impostor(Generator):
        id = "props"

        def generate(self, seed, count, frame_px, params, base=0):
            return []

    fake_eps(FakeEntryPoint(Impostor))
    monkeypatch.setattr(plugins, "discover", lambda group: {"props": Impostor})
    registry: dict = dict(BUILTIN_GENERATORS)
    assert plugins.load_into(registry) == []
    assert registry["props"] is BUILTIN_GENERATORS["props"]


def test_plugin_ids_exclude_builtins(monkeypatch):
    monkeypatch.setattr(plugins, "discover", lambda group: {
        "vehicle": Vehicle, "props": BUILTIN_GENERATORS["props"]})
    monkeypatch.setattr(reg, "GENERATORS", dict(reg.BUILTIN_GENERATORS))
    plugins.load_into(reg.GENERATORS)
    assert plugin_generator_ids() == ["vehicle"]


# ── Registry integration ───────────────────────────────────────────────

def test_registry_contains_all_builtins():
    for gen_id, cls in BUILTIN_GENERATORS.items():
        assert GENERATORS[gen_id] is cls
        assert get_generator(gen_id) is cls


def test_every_builtin_declares_a_param_surface():
    for gen_id, cls in BUILTIN_GENERATORS.items():
        assert isinstance(cls.PARAMS, frozenset), gen_id
        assert cls.PARAMS, f"{gen_id} declares an empty param surface"


def test_accepts_is_empty_for_declared_params():
    assert Vehicle.accepts({"wheels": 4, "fill": [1, 2, 3]}) == ()


def test_accepts_reports_unknown_params():
    assert Vehicle.accepts({"wheel": 4}) == ("wheel",)


def test_framework_params_are_always_allowed():
    """`palette`/`autotile` belong to the framework, not the generator."""
    assert Vehicle.accepts({"palette": "earth", "autotile": 16}) == ()


def test_paramsless_plugin_skips_validation():
    """PARAMS=None disables the check so old plug-ins keep working."""
    assert Paramsless.accepts({"anything": 1, "whatever": 2}) == ()


def test_nameless_generators_are_not_registered():
    assert "" not in BUILTIN_GENERATORS


# ── Spec-level behaviour with a plug-in ────────────────────────────────

def test_spec_rejects_unknown_param_for_plugin(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sprout.spec.GENERATORS", {**BUILTIN_GENERATORS, "vehicle": Vehicle})
    p = _spec(tmp_path, '{"whee1s": 4}', generator="vehicle")
    with pytest.raises(SpecError, match="unknown param"):
        load_spec(p)


def test_spec_accepts_declared_plugin_params(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sprout.spec.GENERATORS", {**BUILTIN_GENERATORS, "vehicle": Vehicle})
    p = _spec(tmp_path, '{"wheels": 4}', generator="vehicle")
    assert load_spec(p).items[0].params == {"wheels": 4}


def test_load_into_tolerates_a_broken_discovery(monkeypatch):
    """_load_plugins must never take the CLI down."""

    def _boom(registry, group=plugins.ENTRY_POINT_GROUP):
        raise RuntimeError("discovery exploded")

    monkeypatch.setattr(plugins, "load_into", _boom)
    monkeypatch.setattr(reg, "GENERATORS", dict(reg.BUILTIN_GENERATORS))
    reg._load_plugins()
    assert set(reg.BUILTIN_GENERATORS) <= set(reg.GENERATORS)
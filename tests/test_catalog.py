"""Tests for catalog → spec codegen (`sprout catalog` + --coverage)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sprout.catalog import (
    CatalogError,
    build_spec,
    extract_records,
    load_mapping,
    resolve_items,
)
from sprout.cli import app, _generate
from sprout.spec import load_spec

runner = CliRunner()

CATALOG_JSON = [
    {"key": "paw", "set": "pets", "name": "Paw"},
    {"key": "coin", "set": "treasures", "name": "Coin"},
    {"key": "wave", "set": "glyphs", "name": "Wave"},
]

CATALOG_TS = """\
export const CATALOG = [
  { key: "paw", set: "pets", name: "Paw" },
  { key: "coin", set: "treasures", name: "Coin" },
  { key: "wave", set: "glyphs", name: "Wave" },
];

const LAYOUT = { cols: 4 };
"""

MAPPING = {
    "sets": {
        "pets": {"generator": "critter", "frames": 4,
                 "params": {"archetype": "quadruped"}},
        "glyphs": {"generator": "font", "params": {"chars": "w"}},
    },
    "ids": {
        "coin": {"generator": "props",
                 "params": {"kind": "treasure", "form": "coin"}},
    },
    "default": {"generator": "props", "params": {"kind": "rock"}},
    "skip": [],
}


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# ── extraction ─────────────────────────────────────────────────────────
def test_extract_json_list(tmp_path: Path) -> None:
    f = _write(tmp_path, "catalog.json", json.dumps(CATALOG_JSON))
    recs = extract_records(f, "key")
    assert [r["key"] for r in recs] == ["paw", "coin", "wave"]


def test_extract_json_wrapped(tmp_path: Path) -> None:
    f = _write(tmp_path, "catalog.json",
               json.dumps({"items": CATALOG_JSON}))
    assert len(extract_records(f, "key")) == 3


def test_extract_ts_flat_objects(tmp_path: Path) -> None:
    f = _write(tmp_path, "catalog.ts", CATALOG_TS)
    recs = extract_records(f, "key")
    assert [r["key"] for r in recs] == ["paw", "coin", "wave"]
    assert all(r["set"] for r in recs)


def test_extract_ts_quoted_keys(tmp_path: Path) -> None:
    src = 'const C = [{ "key": "a" }, { "key": "b" }];'
    f = _write(tmp_path, "catalog.ts", src)
    assert [r["key"] for r in extract_records(f, "key")] == ["a", "b"]


def test_extract_missing_field_raises(tmp_path: Path) -> None:
    f = _write(tmp_path, "catalog.json",
               json.dumps([{"name": "Paw"}, {"name": "Coin"}]))
    with pytest.raises(CatalogError, match="no records with field 'key'"):
        extract_records(f, "key")


def test_extract_duplicate_ids_raise(tmp_path: Path) -> None:
    f = _write(tmp_path, "catalog.json",
               json.dumps([{"key": "paw"}, {"key": "paw"}]))
    with pytest.raises(CatalogError, match="duplicate id 'paw'"):
        extract_records(f, "key")


def test_extract_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="not found"):
        extract_records(tmp_path / "nope.ts", "key")


def test_extract_invalid_json_raises(tmp_path: Path) -> None:
    f = _write(tmp_path, "catalog.json", "{nope")
    with pytest.raises(CatalogError, match="invalid JSON"):
        extract_records(f, "key")


# ── mapping resolution ─────────────────────────────────────────────────
def test_resolve_ids_beat_sets_beat_default() -> None:
    records = [{"key": r["key"], "set": r["set"]} for r in CATALOG_JSON]
    items = resolve_items(records, "key", MAPPING, set_field="set")
    by_id = {i["id"]: i for i in items}
    assert by_id["paw"]["generator"] == "critter"
    assert by_id["paw"]["frames"] == 4
    assert by_id["paw"]["params"]["archetype"] == "quadruped"
    assert by_id["coin"]["generator"] == "props"       # ids rule
    assert by_id["coin"]["params"]["form"] == "coin"
    assert by_id["wave"]["generator"] == "font"


def test_resolve_unmapped_raises() -> None:
    no_default = {"sets": MAPPING["sets"], "ids": MAPPING["ids"]}
    records = [{"key": "ghost", "set": "unknown"}]
    with pytest.raises(CatalogError, match="no mapping for id 'ghost'"):
        resolve_items(records, "key", no_default, set_field="set")


def test_resolve_default_rule_applies() -> None:
    records = [{"key": "paw", "set": "zzz"}]
    items = resolve_items(records, "key", MAPPING, set_field="set")
    assert items[0]["generator"] == "props"
    assert items[0]["params"] == {"kind": "rock"}


def test_resolve_skip_drops_records() -> None:
    mapping = {**MAPPING, "skip": ["wave"]}
    records = [{"key": r["key"], "set": r["set"]} for r in CATALOG_JSON]
    items = resolve_items(records, "key", mapping, set_field="set")
    assert [i["id"] for i in items] == ["paw", "coin"]


def test_resolve_skip_everything_raises() -> None:
    mapping = {**MAPPING, "skip": ["paw", "coin", "wave"]}
    records = [{"key": r["key"], "set": r["set"]} for r in CATALOG_JSON]
    with pytest.raises(CatalogError, match="skips every record"):
        resolve_items(records, "key", mapping, set_field="set")


def test_fallback_generator_without_mapping() -> None:
    records = [{"key": "paw", "set": "pets"}]
    items = resolve_items(records, "key", {}, fallback_generator="props")
    assert items == [{"id": "paw", "generator": "props"}]


def test_load_mapping_rejects_non_object(tmp_path: Path) -> None:
    f = _write(tmp_path, "mapping.json", "[1]")
    with pytest.raises(CatalogError, match="JSON object"):
        load_mapping(f)


# ── spec building ──────────────────────────────────────────────────────
def test_build_spec_shape() -> None:
    items = [{"id": "paw", "generator": "critter"}]
    spec = build_spec(items, name="cat", seed=9, frame_px=96, cols=5)
    assert spec["name"] == "cat"
    assert spec["seed"] == 9
    assert spec["layout"]["framePx"] == 96
    assert spec["layout"]["cols"] == 5
    assert spec["items"] == items


def test_generated_spec_loads_and_renders(tmp_path: Path) -> None:
    cat = _write(tmp_path, "catalog.json", json.dumps(CATALOG_JSON))
    mp = _write(tmp_path, "mapping.json", json.dumps(MAPPING))
    records = extract_records(cat, "key")
    spec = build_spec(resolve_items(records, "key", load_mapping(mp)),
                      name="cat_atlas")
    spec_path = tmp_path / "cat.json"
    spec_path.write_text(json.dumps(spec))
    loaded = load_spec(spec_path)
    assert [i.id for i in loaded.items] == ["paw", "coin", "wave"]
    out = tmp_path / "out"
    _generate(spec_path, out, None, False)
    assert (out / "atlas.png").is_file()


# ── CLI: sprout catalog ────────────────────────────────────────────────
def test_catalog_command_writes_spec(tmp_path: Path) -> None:
    cat = _write(tmp_path, "catalog.ts", CATALOG_TS)
    mp = _write(tmp_path, "mapping.json", json.dumps(MAPPING))
    dest = tmp_path / "specs" / "cat.json"
    r = runner.invoke(app, ["catalog", str(cat), "--field", "key",
                            "--map", str(mp), "--out", str(dest),
                            "--name", "cat_atlas", "--seed", "5"])
    assert r.exit_code == 0, r.output
    assert "3 ids" in r.output
    spec = load_spec(dest)
    assert [i.id for i in spec.items] == ["paw", "coin", "wave"]
    assert spec.seed == 5


def test_catalog_command_deterministic(tmp_path: Path) -> None:
    cat = _write(tmp_path, "catalog.ts", CATALOG_TS)
    mp = _write(tmp_path, "mapping.json", json.dumps(MAPPING))
    outs = []
    for run in ("a", "b"):
        dest = tmp_path / f"{run}.json"
        r = runner.invoke(app, ["catalog", str(cat), "--field", "key",
                                "--map", str(mp), "--out", str(dest)])
        assert r.exit_code == 0, r.output
        outs.append(dest.read_bytes())
    assert outs[0] == outs[1]


def test_catalog_command_without_map_uses_generator(tmp_path: Path) -> None:
    cat = _write(tmp_path, "catalog.json", json.dumps(CATALOG_JSON))
    dest = tmp_path / "cat.json"
    r = runner.invoke(app, ["catalog", str(cat), "--field", "key",
                            "--generator", "props", "--out", str(dest)])
    assert r.exit_code == 0, r.output
    assert all(i["generator"] == "props"
               for i in json.loads(dest.read_text())["items"])


def test_catalog_command_unmapped_id_exits_1(tmp_path: Path) -> None:
    cat = _write(tmp_path, "catalog.json",
                 json.dumps([{"key": "ghost", "set": "zzz"}]))
    mp = _write(tmp_path, "mapping.json",
                json.dumps({"sets": MAPPING["sets"], "ids": MAPPING["ids"]}))
    r = runner.invoke(app, ["catalog", str(cat), "--field", "key",
                            "--map", str(mp), "--out",
                            str(tmp_path / "x.json")])
    assert r.exit_code == 1
    assert "no mapping" in r.output


def test_catalog_command_missing_field_exits_1(tmp_path: Path) -> None:
    cat = _write(tmp_path, "catalog.json", json.dumps([{"name": "x"}]))
    r = runner.invoke(app, ["catalog", str(cat), "--field", "key",
                            "--generator", "props", "--out",
                            str(tmp_path / "x.json")])
    assert r.exit_code == 1
    assert "no records with field" in r.output


# ── CLI: validate --coverage ───────────────────────────────────────────
def _make_spec(tmp_path: Path, ids: list[str]) -> Path:
    items = [{"id": i, "generator": "props", "params": {"kind": "rock"}}
             for i in ids]
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(build_spec(items, name="cov")))
    return p


def test_coverage_pass(tmp_path: Path) -> None:
    cat = _write(tmp_path, "catalog.json", json.dumps(CATALOG_JSON))
    spec = _make_spec(tmp_path, ["paw", "coin", "wave"])
    r = runner.invoke(app, ["validate", str(spec), "--coverage", str(cat),
                            "--field", "key"])
    assert r.exit_code == 0, r.output
    assert "coverage 3/3" in r.output


def test_coverage_missing_exits_1(tmp_path: Path) -> None:
    cat = _write(tmp_path, "catalog.json", json.dumps(CATALOG_JSON))
    spec = _make_spec(tmp_path, ["paw", "coin"])
    r = runner.invoke(app, ["validate", str(spec), "--coverage", str(cat),
                            "--field", "key"])
    assert r.exit_code == 1
    assert "coverage 2/3" in r.output
    assert "wave" in r.output


def test_coverage_skip_ids(tmp_path: Path) -> None:
    cat = _write(tmp_path, "catalog.json", json.dumps(CATALOG_JSON))
    mp = _write(tmp_path, "mapping.json",
                json.dumps({**MAPPING, "skip": ["wave"]}))
    spec = _make_spec(tmp_path, ["paw", "coin"])
    r = runner.invoke(app, ["validate", str(spec), "--coverage", str(cat),
                            "--field", "key", "--map", str(mp)])
    assert r.exit_code == 0, r.output
    assert "coverage 2/2" in r.output


def test_coverage_requires_field(tmp_path: Path) -> None:
    cat = _write(tmp_path, "catalog.json", json.dumps(CATALOG_JSON))
    spec = _make_spec(tmp_path, ["paw"])
    r = runner.invoke(app, ["validate", str(spec), "--coverage", str(cat)])
    assert r.exit_code == 1
    assert "--field" in re.sub(r"\x1b\[[0-9;]*m", "", r.output)


def test_validate_without_coverage_unchanged(tmp_path: Path) -> None:
    spec = _make_spec(tmp_path, ["paw"])
    r = runner.invoke(app, ["validate", str(spec)])
    assert r.exit_code == 0, r.output
    assert "coverage" not in r.output

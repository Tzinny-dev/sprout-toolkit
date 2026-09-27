"""Catalog → spec codegen (generic, tool-agnostic).

`sprout catalog` extracts unique ids from any catalog file (`.json` or a
flat-object `.ts`/`.js` list) and materializes a spec by applying an
external `mapping.json`. The toolkit never learns the catalog's domain:
the mapping (sets → generator + params, per-id overrides, skip list)
lives on the consumer's side of the fence.

mapping.json shape:
  {
    "sets":    { "<set>": { "generator": "...", "frames": 4,
                            "params": { ... } } },
    "ids":     { "<id>":   { "generator": "...", "params": { ... } } },
    "default": { "generator": "..." },
    "skip":    ["<id>", "..."]
  }
Resolution per record: ids[id] > sets[record.set] > default > error.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Flat object literals only: `{ key: "vaca", set: "pets" }` — nested
# blocks are skipped on purpose (they are config, not records).
_RECORD_RE = re.compile(r"\{[^{}]*\}")
_PAIR_RE = re.compile(r"[\"']?([\w-]+)[\"']?\s*:\s*[\"']([^\"']*)[\"']")
_WRAPPED_KEYS = ("items", "entries", "records", "data", "list", "catalog")
_SPEC_KEYS = ("name", "seed", "target", "files", "layout", "items")


class CatalogError(ValueError):
    """Bad catalog file, mapping, or resolution rule."""


def _pairs(block: str) -> dict[str, str]:
    return dict(_PAIR_RE.findall(block))


def extract_records(path: Path, field: str) -> list[dict[str, Any]]:
    """Return records carrying `field` (other blocks are not records)."""
    if not path.is_file():
        raise CatalogError(f"catalog file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        records = _json_records(path, text)
    else:
        records = [_pairs(b) for b in _RECORD_RE.findall(text)]
    kept = [r for r in records if str(r.get(field, "")).strip()]
    if not kept:
        raise CatalogError(f"no records with field '{field}' in {path}")
    seen: set[str] = set()
    for rec in kept:
        rid = str(rec[field])
        if rid in seen:
            raise CatalogError(f"duplicate id '{rid}' in {path}")
        seen.add(rid)
    return kept


def _json_records(path: Path, text: str) -> list[Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise CatalogError(f"invalid JSON in {path}: {e}") from None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in _WRAPPED_KEYS:
            if isinstance(data.get(key), list):
                return data[key]
        raise CatalogError(
            f"{path}: expected a list of records or one of "
            f"{', '.join(_WRAPPED_KEYS)}")
    raise CatalogError(f"{path}: expected a list of records")


def load_mapping(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.is_file():
        raise CatalogError(f"mapping file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CatalogError(f"invalid JSON in {path}: {e}") from None
    if not isinstance(data, dict):
        raise CatalogError(f"{path}: mapping must be a JSON object")
    return data


def record_ids(records: list[dict[str, Any]], field: str) -> list[str]:
    return [str(r[field]) for r in records]


def resolve_items(
    records: list[dict[str, Any]],
    field: str,
    mapping: dict[str, Any],
    *,
    set_field: str = "set",
    fallback_generator: str | None = None,
) -> list[dict[str, Any]]:
    """Apply the mapping to every record; returns spec items (order kept)."""
    sets = mapping.get("sets") or {}
    ids_map = mapping.get("ids") or {}
    default = mapping.get("default") or {}
    skip = set(mapping.get("skip") or [])
    items: list[dict[str, Any]] = []
    for rec in records:
        rid = str(rec[field])
        if rid in skip:
            continue
        rule = ids_map.get(rid) or sets.get(str(rec.get(set_field, ""))) \
            or default
        if not rule and fallback_generator:
            rule = {"generator": fallback_generator}
        if not isinstance(rule, dict) or not rule.get("generator"):
            raise CatalogError(
                f"no mapping for id '{rid}' (set "
                f"'{rec.get(set_field, '')}'): add it to 'ids', 'sets' or "
                f"'default' in the mapping")
        item: dict[str, Any] = {"id": rid, "generator": str(rule["generator"])}
        if rule.get("frames"):
            item["frames"] = int(rule["frames"])
        if rule.get("params"):
            item["params"] = dict(rule["params"])
        items.append(item)
    if not items:
        raise CatalogError("mapping skips every record — nothing to emit")
    return items


def build_spec(
    items: list[dict[str, Any]],
    *,
    name: str,
    seed: int = 0,
    frame_px: int = 64,
    cols: int = 8,
) -> dict[str, Any]:
    return {
        "name": name,
        "seed": seed,
        "target": "expo-rn-skia",
        "files": {"atlas": "atlas.png"},
        "layout": {"framePx": frame_px, "cols": cols,
                   "tileLogical": 32, "sample": "nearest"},
        "items": items,
    }


def write_spec(spec: dict[str, Any], out: Path) -> None:
    for key in _SPEC_KEYS:
        if key not in spec:
            raise CatalogError(f"internal: spec missing '{key}'")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")


def coverage(
    spec_path: Path,
    catalog_path: Path,
    field: str,
    *,
    mapping: dict[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
    """(expected ids, missing ids) — expected ⊆ spec items."""
    from .spec import load_spec  # local import to avoid cycles

    records = extract_records(catalog_path, field)
    skip = set((mapping or {}).get("skip") or [])
    expected = [i for i in record_ids(records, field) if i not in skip]
    have = {i.id for i in load_spec(spec_path).items}
    missing = [i for i in expected if i not in have]
    return expected, missing

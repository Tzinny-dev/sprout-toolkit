"""Data-driven vocabularies: packaged defaults + consumer overrides.

A vocabulary is a JSON file under ``sprout/assets/vocab/``. Generators load
it instead of hardcoding the word list, so a consumer can extend the
toolkit's forms without forking it: point ``SPROUT_VOCAB_DIR`` at a
directory holding same-named JSON files and the two are deep-merged, with
the consumer's values winning.

Lists are replaced wholesale (a form list is a complete set, not something
to merge element-wise); dicts merge recursively, so adding one mood does
not require restating the other fifteen.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "vocab"
OVERRIDE_ENV = "SPROUT_VOCAB_DIR"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursive merge; lists are replaced, dicts merge key by key."""
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _normalize(obj: Any) -> Any:
    """Convert JSON lists to the tuples the generators expect.

    Colors are ``[r, g, b]`` in JSON and ``(r, g, b)`` in the code; PIL
    rejects a list where a color tuple is required. Three-int lists become
    tuples; everything else passes through so form lists stay lists.
    """
    if isinstance(obj, list):
        if len(obj) == 3 and all(isinstance(x, int) for x in obj):
            return tuple(obj)
        return [_normalize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    return obj


def load(name: str) -> dict[str, Any]:
    """Load a vocabulary: packaged default merged with the override dir."""
    data = _read(ASSETS_DIR / f"{name}.json")
    override_dir = os.environ.get(OVERRIDE_ENV)
    if override_dir:
        path = Path(override_dir) / f"{name}.json"
        if path.is_file():
            data = _deep_merge(data, _read(path))
    return _normalize(data)


def override_dir() -> str | None:
    """The active override directory, or None."""
    return os.environ.get(OVERRIDE_ENV)

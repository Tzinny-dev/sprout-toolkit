"""Tests de validación de spec."""
from __future__ import annotations

import json
import pytest

from sprout.spec import SpecError, load_spec


def _write(tmp_path, spec: dict):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(spec))
    return p


def test_load_valid(tmp_path) -> None:
    spec = {
        "name": "demo_atlas", "seed": 7, "layout": {"cols": 4}, "items": [
            {"id": "hero", "generator": "blob_walk", "frames": 8},
            {"id": "tiles", "generator": "terrain", "frames": 8},
        ],
        "animations": {"walk": {"frames": "hero", "fps": 8}},
    }
    s = load_spec(_write(tmp_path, spec))
    assert s.total_frames == 16
    assert s.filename == "demo_atlas_atlas.png"
    assert s.layout.sample == "nearest"


def test_unknown_generator_rejected(tmp_path) -> None:
    spec = {"name": "x", "seed": 1, "layout": {"cols": 4},
            "items": [{"id": "a", "generator": "magia", "frames": 1}]}
    with pytest.raises(SpecError, match="magia"):
        load_spec(_write(tmp_path, spec))


def test_duplicate_item_ids_rejected(tmp_path) -> None:
    spec = {"name": "x", "seed": 1, "layout": {"cols": 4}, "items": [
        {"id": "a", "generator": "terrain", "frames": 1},
        {"id": "a", "generator": "terrain", "frames": 1},
    ]}
    with pytest.raises(SpecError, match="duplicados"):
        load_spec(_write(tmp_path, spec))


def test_anim_references_missing_item(tmp_path) -> None:
    spec = {"name": "x", "seed": 1, "layout": {"cols": 4},
            "items": [{"id": "a", "generator": "terrain", "frames": 1}],
            "animations": {"idle": {"frames": "ghost"}}}
    with pytest.raises(SpecError, match="ghost"):
        load_spec(_write(tmp_path, spec))


def test_negative_seed_rejected(tmp_path) -> None:
    spec = {"name": "x", "seed": -1, "layout": {"cols": 4},
            "items": [{"id": "a", "generator": "terrain", "frames": 1}]}
    with pytest.raises(SpecError, match="seed"):
        load_spec(_write(tmp_path, spec))


def test_bad_sample_rejected(tmp_path) -> None:
    spec = {"name": "x", "seed": 1, "items": [{"id": "a", "generator": "terrain", "frames": 1}],
            "layout": {"sample": "muy"}}
    with pytest.raises(SpecError, match="sample"):
        load_spec(_write(tmp_path, spec))
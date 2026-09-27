"""Fase 8: npm wrapper sync + manifest schemaVersion."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from PIL import Image

from sprout import __version__
from sprout.exporter import build_manifest
from sprout.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]  # repo root (pyproject, npm/, docs/)
NPM = ROOT / "npm"
SPEC = ROOT / "specs" / "demo.json"


def test_npm_wrapper_version_matches_python() -> None:
    """package.json version == pyproject version == sprout.__version__."""
    if not NPM.is_dir():
        pytest.skip("npm/ wrapper not present (installed from sdist?)")
    pkg = json.loads((NPM / "package.json").read_text())
    pyproject = (ROOT / "pyproject.toml").read_text()
    m = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    assert m, "pyproject version not found"
    assert pkg["version"] == m.group(1) == __version__


def test_npm_wrapper_bin_spawns_sprout() -> None:
    if not NPM.is_dir():
        pytest.skip("npm/ wrapper not present (installed from sdist?)")
    src = (NPM / "bin" / "sprout.js").read_text()
    assert "'-m', 'sprout'" in src or '"-m", "sprout"' in src
    assert "--version" in src
    assert "sprout-toolkit==" in src  # pinned install hint
    assert pkg_bin_target(NPM / "package.json") == "bin/sprout.js"


def pkg_bin_target(package_json: Path) -> str:
    return json.loads(package_json.read_text())["bin"]["sprout"]


def test_manifest_declares_schema_version() -> None:
    """schemaVersion is the compatibility lever (policy: CHANGELOG/docs)."""
    s = load_spec(SPEC)
    records = [{"id": "x", "col": 0, "row": 0, "x": 0, "y": 0,
                "w": 64, "h": 64}]
    sheet = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    m = build_manifest(s, records, "a.png", sheet, "specs/demo.json")
    assert m["schema"] == "sprout/manifest@0"
    assert m["schemaVersion"] == 1

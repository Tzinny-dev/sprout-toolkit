"""Model and validation for the `spec.json` input contract (schema v0).

Example:
{
  "name": "demo_atlas",
  "seed": 1337,
  "target": "expo-rn-skia",
  "files": { "atlas": "atlas.png" },          // optional; default "<name>_atlas.png"
  "layout": { "framePx": 64, "cols": 4, "tileLogical": 32, "sample": "nearest" },
  "items": [
    { "id": "hero",  "generator": "blob_walk", "frames": 8 },
    { "id": "tiles", "generator": "terrain",  "tiles": 8 }
  ],
  "animations": { "walk": { "frames": "hero", "fps": 8, "loop": true } }
}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .generators import GENERATORS
from . import sksl


class SpecError(ValueError):
    """Invalid spec."""


@dataclass
class Layout:
    frame_px: int = 64
    cols: int = 0
    tile_logical: int = 32
    sample: str = "nearest"

    def resolve_rows(self, total_frames: int) -> int:
        return -(-total_frames // self.cols)  # ceil


@dataclass
class Item:
    id: str
    generator: str
    frames: int = 1
    params: dict = field(default_factory=dict)
    autotile: int | None = None


@dataclass
class Anim:
    frames: str
    fps: int = 8
    loop: bool = True


@dataclass
class Spec:
    name: str
    seed: int
    items: list[Item]
    layout: Layout
    animations: dict[str, Anim]
    runtime: dict | None = None
    files_atlas: str = ""
    target: str = "expo-rn-skia"

    @property
    def filename(self) -> str:
        return self.files_atlas or f"{self.name}_atlas.png"

    @property
    def total_frames(self) -> int:
        return sum(i.frames for i in self.items)


def _expect(d: dict, keys: tuple[str, ...]) -> None:
    for k in keys:
        if k not in d:
            raise SpecError(f"missing field '{k}'")


def load_spec(path: Path) -> Spec:
    if not path.is_file():
        raise SpecError(f"spec not found: {path}")
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SpecError(f"invalid JSON in {path}: {e}") from e
    if not isinstance(raw, dict):
        raise SpecError("the spec must be a JSON object")

    _expect(raw, ("name", "seed", "items"))
    name = raw["name"]
    if not name.replace("_", "").replace("-", "").isalnum():
        raise SpecError(f"invalid name: '{name}' (alphanumeric, '_' and '-' only)")

    seed = raw["seed"]
    if not isinstance(seed, int) or seed < 0:
        raise SpecError(f"seed must be an integer >= 0, received {seed!r}")

    layout_raw = raw.get("layout", {}) or {}
    layout = Layout(
        frame_px=int(layout_raw.get("framePx", 64)),
        cols=int(layout_raw.get("cols", 0)),
        tile_logical=int(layout_raw.get("tileLogical", 32)),
        sample=str(layout_raw.get("sample", "nearest")),
    )
    if layout.frame_px <= 0:
        raise SpecError("layout.framePx must be > 0")
    if layout.tile_logical <= 0:
        raise SpecError("layout.tileLogical must be > 0")
    if layout.sample not in ("nearest", "linear"):
        raise SpecError(f"invalid layout.sample: {layout.sample!r} (nearest|linear)")
    if layout.cols <= 0:
        raise SpecError("layout.cols must be > 0 (defines the spritesheet grid)")

    items: list[Item] = []
    seen: set[str] = set()
    for it in raw["items"]:
        it_id = it.get("id")
        if not isinstance(it_id, str) or not it_id:
            raise SpecError("each item requires an alphanumeric id")
        if it_id in seen:
            raise SpecError(f"duplicate ids among items: '{it_id}'")
        seen.add(it_id)
        gen = it.get("generator", it_id)
        if gen not in GENERATORS:
            raise SpecError(
                f"unknown generator '{gen}' in item '{it_id}' "
                f"(available: {', '.join(sorted(GENERATORS))})"
            )
        n = int(it.get("frames", 1))
        if n <= 0:
            raise SpecError(f"item '{it_id}': frames must be > 0")

        auto_raw = it.get("autotile")
        autotile: int | None = None
        if auto_raw is not None:
            if str(auto_raw) not in ("16", "47"):
                raise SpecError(
                    f"item '{it_id}': invalid autotile {auto_raw!r} (16 | 47 | null)"
                )
            autotile = int(str(auto_raw))
            if gen != "terrain":
                raise SpecError(
                    f"item '{it_id}': autotile is only supported by the 'terrain' generator"
                )
            if n != autotile:
                raise SpecError(
                    f"item '{it_id}': autotile {autotile} requires frames={autotile} "
                    f"(received {n})"
                )

        it_params = dict(it.get("params", {}) or {})
        if autotile is not None:
            it_params["autotile"] = autotile
        items.append(Item(id=it_id, generator=gen, frames=n,
                          params=it_params, autotile=autotile))

    animations: dict[str, Anim] = {}
    for name_a, a in (raw.get("animations", {}) or {}).items():
        frames_source = a.get("frames", name_a)
        if frames_source not in seen:
            raise SpecError(
                f"animation '{name_a}' points to a nonexistent item: '{frames_source}'"
            )
        animations[name_a] = Anim(
            frames=frames_source,
            fps=int(a.get("fps", 8)),
            loop=bool(a.get("loop", True)),
        )

    try:
        runtime = sksl.normalize_params(raw.get("runtime", False))
    except ValueError as e:
        raise SpecError(f"invalid runtime: {e}") from e

    files_atlas = ""
    files_raw = raw.get("files") or {}
    files_atlas = str(files_raw.get("atlas", ""))

    return Spec(
        name=name,
        seed=seed,
        items=items,
        layout=layout,
        animations=animations,
        runtime=runtime,
        files_atlas=files_atlas,
        target=str(raw.get("target", "expo-rn-skia")),
    )
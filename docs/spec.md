# Spec schema (v0)

A spec is a single JSON file describing which assets to generate from which
seed. Validation is strict: any unknown generator, duplicate id or bad value
fails `sprout validate` / `generate` with a descriptive error.

## Required fields

```json
{
  "name": "starter_atlas",
  "seed": 7,
  "items": [
    { "id": "hero", "generator": "blob_walk", "frames": 8 }
  ]
}
```

| field | type | rules |
|---|---|---|
| `name` | string | alphanumeric + `_` / `-` only |
| `seed` | integer | `>= 0` — same seed ⇒ same pixels |
| `items` | array | at least one item, each with a unique `id` |

## Layout

```json
"layout": { "framePx": 64, "cols": 4, "tileLogical": 32, "sample": "nearest" }
```

| field | default | rules |
|---|---|---|
| `framePx` | `64` | `> 0` — pixels per frame in the atlas |
| `cols` | — | **required**, `> 0` — spritesheet grid columns (rows = ceil(total / cols)) |
| `tileLogical` | `32` | `> 0` — logical tile size on screen (`frameScale = tileLogical / framePx`) |
| `sample` | `nearest` | `nearest` \| `linear` — sampling mode for Skia |

## Items

```json
{ "id": "tiles", "generator": "terrain", "frames": 47, "autotile": 47 }
```

| field | default | rules |
|---|---|---|
| `id` | — | required, unique, non-empty string |
| `generator` | `id` | must exist in the registry (`terrain`, `blob_walk`, `props`, `particles`, `ui`, `font`) |
| `frames` | `1` | `> 0` |
| `params` | `{}` | generator-specific — see [Generators](/docs/generators) |
| `autotile` | `null` | `16` \| `47`; only for `terrain`; requires `frames` == variant count |

## Animations

```json
"animations": { "walk": { "frames": "hero", "fps": 8, "loop": true } }
```

| field | default | rules |
|---|---|---|
| `frames` | the animation's own name | must reference an existing item `id` |
| `fps` | `8` | integer |
| `loop` | `true` | boolean |

## Runtime shader (optional)

Emits a tileable FBM SkSL shader (`<name>.sksl` + `shader` block in the
manifest). Accepts `false` (default), `true` (defaults), or an object:

| field | default | rules |
|---|---|---|
| `freq` | `0.05` | `> 0` |
| `octaves` | `4` | `1..8` |
| `tileable` | `true` | boolean |
| `base` | `[0.16, 0.27, 0.16]` | `[r, g, b]` in 0..1 |
| `accent` | `[0.90, 0.79, 0.46]` | `[r, g, b]` in 0..1 |

```json
"runtime": { "freq": 0.05, "octaves": 4, "tileable": true }
```

## Top-level optional fields

| field | default | description |
|---|---|---|
| `target` | `expo-rn-skia` | emit target marker (informational) |
| `files.atlas` | `<name>_atlas.png` | output PNG filename |
| `layout` / `animations` / `runtime` | see above | optional blocks |

## Full example

```json
{
  "name": "starter_atlas",
  "seed": 7,
  "target": "expo-rn-skia",
  "files": { "atlas": "atlas.png" },
  "layout": { "framePx": 64, "cols": 4, "tileLogical": 32, "sample": "nearest" },
  "items": [
    { "id": "hero",  "generator": "blob_walk", "frames": 8 },
    { "id": "coin",  "generator": "props", "frames": 4, "params": { "kind": "flower" } }
  ],
  "animations": { "walk": { "frames": "hero", "fps": 8, "loop": true } },
  "runtime": false
}
```

Check it with `sprout validate starter.json`. A runnable walkthrough lives in
the [10-minute quickstart](/docs/quickstart).

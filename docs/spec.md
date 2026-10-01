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
| `sample` | `nearest` | `nearest` \| `linear` — sampling mode for Skia; `linear` suits displaying a frame larger than its native `framePx` (e.g. a smaller tier upscaled) |

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
| `tint` | `none` | `none` \| `shade` \| `full` — declares the item as tintable (see [Runtime tint](#runtime-tint-optional)) |

## Runtime tint (optional)

Color variants are **not** baked into the atlas: the item is generated once
in a tint-ready palette and recolored at runtime with `colorMatrixFor` /
`tintColors` (exported by `index.ts`). One sprite + N runtime colors instead
of N baked copies.

```json
{
  "colors": [
    { "key": "ember", "hex": "#E4572E" },
    { "key": "azure", "hex": "#3E8FD0" }
  ],
  "items": [
    { "id": "hero", "generator": "blob_walk", "frames": 4, "tint": "shade" }
  ]
}
```

| field | default | rules |
|---|---|---|
| `colors` | `[]` | list of `{ "key", "hex" }`; `key` unique; `hex` is `#RGB`/`#RRGGBB` (normalized to `#RRGGBB`) |
| item `tint` | `none` | `none` = colors are baked; `shade` = tint preserves luminance (correct on colored art); `full` = pure multiply (identical to `shade` on neutral/tint-ready art) |

`sprout lint` reports the uncompressed atlas size against a budget
(`--max-atlas-mb`, default 16 MB) — tinted specs stay at one copy of the art.

## Palettes (optional)

`params.palette` fills in any color role (`fill`, `accent`, `outline`) the
item did not set explicitly — explicit `params.fill`/`outline` always win:

```json
{ "id": "rock", "generator": "props", "params": { "kind": "rock", "palette": "earth" } }
```

Built-in palettes: `earth`, `forest`, `ocean`, `candy`. The outline rule is
`outline = darken(fill, 0.55)`, so every palette stays consistent.

## Params are validated

Each generator declares the `params` keys it reads, so a misspelled key
fails at load time rather than silently rendering a default sprite. This
matters most for specs generated from a catalog by `sprout catalog`, where
a typo would otherwise survive all the way into the atlas:

```console
$ sprout validate specs/catalog.json
invalid: item 'frutilla': unknown param(s) for 'props': 'forma'
         (known: accent, autotile, fill, form, kind, outline, palette)
```

`palette` and `autotile` belong to the framework, not to a generator, so
they are accepted everywhere. Plug-in generators that do not declare
`PARAMS` are not checked.

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

## Tier shaders (optional)

Named effect overlays — one `<name>.<tier>.sksl` each, a `tiers` block in
the manifest, and `TIER_SHADERS` / `tierUniforms()` in `index.ts`. Each
entry maps *your own* tier name to a template:

| template | effect |
|---|---|
| `holographic` | iridescent moving bands |
| `neon` | pulsing glow lines |
| `legend-glow` | breathing glow + sparkles |
| `invisible` | alpha-0 helper (covers nothing — trivial baseline) |

```json
"tiers": {
  "holo": "holographic",
  "boost": { "template": "neon", "speed": 2.0, "glow": 0.8 },
  "legend": "legend-glow"
}
```

| param | default | rules |
|---|---|---|
| `speed` | template's | `>= 0` — animation rate |
| `glow` | template's | `0..1` — overlay opacity |

Tier names: `[A-Za-z0-9_-]`, max 32 chars. Uniforms are seed-derived and
live in `manifest.tiers.<name>.uniforms`; drive them with
`tierUniforms(name, time)`.

## Top-level optional fields

| field | default | description |
|---|---|---|
| `target` | `expo-rn-skia` | emit target marker (informational) |
| `files.atlas` | `<name>_atlas.png` | output PNG filename |
| `colors` | `[]` | runtime tint palette (see [Runtime tint](#runtime-tint-optional)) |
| `layout` / `animations` / `runtime` / `tiers` | see above | optional blocks |

## Full example

```json
{
  "name": "starter_atlas",
  "seed": 7,
  "target": "expo-rn-skia",
  "files": { "atlas": "atlas.png" },
  "layout": { "framePx": 64, "cols": 4, "tileLogical": 32, "sample": "nearest" },
  "colors": [ { "key": "ember", "hex": "#E4572E" } ],
  "items": [
    { "id": "hero",  "generator": "blob_walk", "frames": 8, "tint": "shade" },
    { "id": "coin",  "generator": "props", "frames": 4,
      "params": { "kind": "flower", "palette": "candy" } }
  ],
  "animations": { "walk": { "frames": "hero", "fps": 8, "loop": true } },
  "runtime": false
}
```

Check it with `sprout validate starter.json`. A runnable walkthrough lives in
the [10-minute quickstart](/docs/quickstart).

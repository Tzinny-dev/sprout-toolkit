# Generators reference

Each spec item selects a generator by name. Params live under
`item.params`; colors are `[r, g, b]` arrays (0–255). Defaults below are the
values applied when a param is omitted.

| `generator` | Description | Frames |
|---|---|---|
| `terrain` | Seamless noise tiles + 16/47 autotile | any (47 or 16 with `autotile`) |
| `blob_walk` | 8-frame walk cycle (hero blob) | 8 |
| `props` | Static objects with anchor points | any |
| `particles` | Animated bursts with easing | any |
| `ui` | Button / slider / 9-patch panel | see per-kind |
| `font` | Bitmap font from TTF, one glyph per frame | `len(chars)` |

## `terrain`

Seamless value-noise tiles. With `"autotile": 16` or `47` the item becomes an
autotile set (`frames` must equal the variant count) and the manifest gains an
`autotile` block for `mask → frame` lookup.

| param | default | description |
|---|---|---|
| `contrast` | `0.85` | palette contrast |
| `lift` | `0.075` | brightness lift |
| `cells` | `3` | noise cell density |
| `octaves` | `4` | FBM octaves |
| `bevel` | `0.16` | edge bevel amount |
| `autotile` | — | `16` \| `47` (also settable at item level) |

## `blob_walk`

8-frame walk cycle. Legs swing with `sin(tau*t)` and the body scales — byte
parity with the demo prototype.

| param | default `[r,g,b]` | description |
|---|---|---|
| `body` | `[244, 162, 97]` | body fill |
| `outline` | `[46, 36, 24]` | outline + legs |
| `belly` | `[226, 122, 63]` | belly patch |

## `props`

Static objects. Every frame carries an **anchor point**
(`frames[].anchor` in the manifest, computed from the rendered alpha bbox) —
the point where the object touches the ground, for tilemap-aligned placement.

| param | default | description |
|---|---|---|
| `kind` | `rock` | `rock` \| `bush` \| `chest` \| `mushroom` \| `flower` |
| `fill` | per-kind | `[r, g, b]` fill override |
| `outline` | per-kind | `[r, g, b]` outline override |

## `particles`

Animated one-shot bursts with easing.

| param | default | description |
|---|---|---|
| `kind` | `spark` | `spark` \| `smoke` \| `dust` \| `bubble` |
| `particles` | `12` | particle count (min 2) |
| `core` | per-kind | `[r, g, b]` core color |
| `trail` | per-kind | `[r, g, b]` trail color |

Per-kind default colors: spark `(255,235,130)/(255,130,30)`,
smoke `(205,205,210)/(110,110,118)`, dust `(200,180,150)/(135,115,90)`,
bubble `(225,245,255)/(120,185,235)`.

## `ui`

| param | default | description |
|---|---|---|
| `kind` | `button` | `button` \| `slider` \| `panel` |
| `fill` | per-kind | `[r, g, b]` fill override |
| `outline` | per-kind | `[r, g, b]` outline override |
| `accent` | per-kind | `[r, g, b]` accent (slider knob) |

Frames per kind:

- **button**: cycles states normal → hover → pressed (`i % 3`); use `frames=3`.
- **slider**: `frames` ≥ 2 progress steps (`0 → 1`).
- **panel**: **requires `frames=9`** (9-patch: corners, edges, center).

## `font`

Bitmap font from a TTF file — one glyph per frame, with advance metrics in
the manifest (`font` block), so text layout needs no native APIs.

| param | default | description |
|---|---|---|
| `chars` | printable ASCII (32–126) | string of glyphs to render |
| `font_path` | bundled DejaVu Sans Mono Bold | path to a `.ttf` |
| `size` | `framePx * 0.6` | point size |
| `fill` | `[255, 255, 255]` | `[r, g, b]` glyph color |

`frames` must equal `len(chars)`.

## Example

```json
{
  "name": "props_atlas",
  "seed": 2024,
  "layout": { "framePx": 64, "cols": 6, "tileLogical": 32, "sample": "nearest" },
  "items": [
    { "id": "rock",  "generator": "props", "frames": 6, "params": { "kind": "rock" } },
    { "id": "chest", "generator": "props", "frames": 4, "params": { "kind": "chest", "fill": [160, 110, 50] } }
  ]
}
```

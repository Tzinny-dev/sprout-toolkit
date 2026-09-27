# Generators reference

Each spec item selects a generator by name. Params live under
`item.params`; colors are `[r, g, b]` arrays (0–255). Defaults below are the
values applied when a param is omitted.

Any generator that takes `fill`/`outline` also accepts
`"params": { "palette": "earth" }` to fill in unset color roles
(`earth`, `forest`, `ocean`, `candy`) — explicit params always win.
See [spec schema](/docs/spec) for `colors` + `tint` (runtime recoloring).

| `generator` | Description | Frames |
|---|---|---|
| `terrain` | Seamless noise tiles + 16/47 autotile | any (47 or 16 with `autotile`) |
| `blob_walk` | 8-frame walk cycle (hero blob) | 8 |
| `props` | Static objects with anchor points | any |
| `critter` | Parametric animals (5 archetypes + parts) | any (idle) |
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

## `critter`

Parametric creatures. Five body plans — `quadruped`, `bird`, `fish`,
`reptile` (side view, facing right) and `bug` (top view) — with composable
parts. Anatomy (ears / snout / tail / legs / wings and the size ratios)
derives from the item's **seed slot**, never the frame index, so every frame
of an item is the same species; frames differ only by the idle pose
(breathing sine + a one-frame blink).

`"auto"` lets the seed pick among the archetype's options
(`bird` → fan tail + beak, `reptile` → splayed legs + long tail, …). The
default palette is a neutral warm gray ramp, so `tint: shade` re-hues it
without muddying. Showcase: `docs/showcase/critter.png`.

| param | default | description |
|---|---|---|
| `archetype` | `quadruped` | `quadruped` \| `bird` \| `fish` \| `reptile` \| `bug` |
| `facing` | `right` | `right` \| `left` (horizontal mirror) |
| `ears` | `auto` | `auto` \| `none` \| `round` \| `pointy` \| `long` |
| `snout` | `auto` | `auto` \| `none` \| `short` \| `long` \| `beak` |
| `tail` | `auto` | `auto` \| `none` \| `short` \| `long` \| `bushy` \| `fan` |
| `legs` | `auto` | `auto` \| `none` \| `stubby` \| `thin` \| `splayed` |
| `wings` | `auto` | `auto` \| `none` \| `small` \| `spread` |
| `fill` | `[216, 210, 200]` | `[r, g, b]` body fill |
| `outline` | `[48, 44, 40]` | `[r, g, b]` outline |
| `belly` | `[242, 238, 230]` | `[r, g, b]` belly / muzzle |
| `eye` | `[32, 30, 28]` | pupil |
| `eye_white` | `[255, 255, 255]` | sclera |
| `beak` | `[240, 170, 60]` | beak |

Not every part applies to every archetype (`bug` ignores `snout`/`tail`,
`fish` ignores `legs`/`ears`) — the value is validated against the part's
own vocabulary, not per archetype. Example spec: `specs/critter.json`.

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

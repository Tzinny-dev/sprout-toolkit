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
| `props` | Static objects: 5 classic kinds + object grammar | any |
| `critter` | Parametric animals (5 archetypes + parts) | any (idle) |
| `flora` | Trees (3 canopies) + forest-floor plants | any (idle or sway) |
| `face` | Emotion faces (16 moods + part overrides) | any (idle + blink) |
| `particles` | Animated bursts with easing | any |
| `ui` | Button / slider / 9-patch panel | see per-kind |
| `font` | Bitmap font from TTF, one glyph per frame | `len(chars)` |

Two keys are handled by the framework rather than by a generator:
`palette` (resolved into unset color roles, see above) and `autotile`
(injected for `terrain` items). Every other key must be in the table of
its generator — an unknown one is rejected at load time instead of being
ignored:

```console
$ sprout validate specs/catalog.json
invalid: item 'frutilla': unknown param(s) for 'props': 'forma'
         (known: accent, autotile, fill, form, kind, outline, palette)
```

## Data-driven vocabularies

Four generators read their word lists from JSON under
`sprout/assets/vocab/` instead of hardcoding them, so a consumer can extend
the toolkit's vocabulary without forking it:

| file | holds |
|---|---|
| `props.json` | `forms` per kind, and the `colors` per form |
| `face.json` | heads, eyes, gazes, mouths, brows, extras, and `moods` |
| `critter.json` | archetypes, per-part options, facings, and the `auto` pick table |
| `flora.json` | canopy, trunk, plant forms, `ages`, and the `age_mods` numbers |

Point `SPROUT_VOCAB_DIR` at a directory holding same-named JSON files and
they are deep-merged over the packaged defaults, consumer values winning.
Lists are replaced wholesale (a form list is a complete set, not something
to merge element-wise); dicts merge key by key, so adding one mood or one
age stage does not mean restating the others. Colors normalize from JSON
`[r, g, b]` to the tuples PIL needs.

```console
$ SPROUT_VOCAB_DIR=./my-vocab sprout validate specs/flora.json
$ # a "colossal" age, declared only in ./my-vocab/flora.json:
$ SPROUT_VOCAB_DIR=./my-vocab sprout generate specs/my-trees.json -o out/
```

A vocabulary extends what a spec is *allowed* to say; it does not extend
what the toolkit can *draw*. Declaring a new option the renderer has no
branch for is accepted and then paints nothing — validation passes, the
frame comes out with that part missing. Pair a new vocabulary entry with
the code that draws it.

## Writing a generator

A generator is a `Generator` subclass: an `id`, the `PARAMS` surface it
reads, and a deterministic `generate(seed, count, frame_px, params, base)`.
Anatomy must derive from the *seed slot* (`seed * 1000 + base`), never the
frame index, so every frame of an item is the same subject and frames
differ only by the idle phase.

To publish it outside this repo, advertise it under the
`sprout.generators` entry-point group:

```toml
[project.entry-points."sprout.generators"]
vehicle = "sprout_vehicles:Vehicle"
```

Installed distributions are discovered on import; `sprout info` lists the
ids they contribute. A plug-in that raises on import, or exposes a
non-`Generator`, is skipped — a broken optional dependency never takes the
built-ins down with it. Built-in ids win a collision, so installing a
plug-in cannot change the output of an existing spec.

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
| `kind` | `rock` | see kinds below |
| `form` | `auto` | v3 kinds: `auto` \| a form of the kind (per-kind) |
| `fill` | per-kind | `[r, g, b]` fill override |
| `accent` | per-kind | `[r, g, b]` secondary color (v3 kinds) |
| `outline` | per-kind | `[r, g, b]` outline override (v3 derives `darken(fill, .55)`) |

**Classic kinds** (single shape, `form` must stay `auto`): `rock`, `bush`,
`chest`, `mushroom`, `flower`.

**v3 object grammar** — parametric food/object families covering flavor
and thing catalog sets; `form: auto` picks a form per variant from the
seed, explicit `form` pins it. Example spec: `specs/objects.json`,
showcase: `docs/showcase/objects.png`.

The vocabulary is data-driven: `props` loads its forms and colors from
`assets/vocab/props.json`, so a consumer can extend it without forking
the toolkit. Point `SPROUT_VOCAB_DIR` at a directory with a same-named
`props.json` and the two are deep-merged (consumer wins):

```json
{
  "forms": { "fruit": ["auto", "apple", "cherry", "dragonfruit"] },
  "colors": { "fruit": { "dragonfruit": { "fill": [200, 50, 200],
                                            "accent": [100, 200, 100] } } }
}
```

Lists are replaced wholesale; dicts merge recursively, so adding one form
or one color does not require restating the rest.

**Where this helps without new code:** `face` moods are combinations of
existing parts, so a new mood in `face.json` works immediately. For
`props`, extending the *colors* of an existing form is enough — a new
*form* also needs a renderer method (`_dragonfruit`) in the generator,
which is what plug-ins (above) are for.

| `kind` | forms |
|---|---|
| `fruit` | `apple` \| `cherry` \| `banana` \| `grapes` \| `strawberry` |
| `sweet` | `candy` \| `donut` \| `cookie` \| `cupcake` \| `lollipop` |
| `potion` | `bottle` \| `flask` \| `vial` |
| `treasure` | `coin` \| `gem` \| `star` \| `ring` |
| `tool` | `hammer` \| `key` \| `pencil` \| `spoon` \| `fork` |
| `paper` | `book` \| `scroll` \| `envelope` |
| `container` | `bag` \| `box` |

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

Those word lists — archetypes, per-part options, facings and the
per-archetype `auto` table — load from `assets/vocab/critter.json`. See
[Data-driven vocabularies](#data-driven-vocabularies).

## `flora`

Trees and forest-floor plants. Anatomy (canopy shape, trunk style, plant
form, proportions) derives from the item's **seed slot**, never the frame
index, so every frame of an item is the *same* plant; frames differ only
by the optional `sway` phase (`sin(tau * i / count)` pivoting at the
ground). Canopies use a union-outline pass — lobes drawn in outline color
first, fill on top — so the silhouette gets a clean ring with no internal
arcs. Showcase: `docs/showcase/flora.png`, `docs/showcase/flora_sway.gif`.

| param | default | description |
|---|---|---|
| `kind` | `tree` | `tree` \| `plant` |
| `canopy` | `auto` | tree: `auto` \| `round` \| `columnar` \| `conifer` |
| `trunk` | `auto` | tree: `auto` \| `straight` \| `gnarled` (lean + kink) |
| `form` | `auto` | plant: `auto` \| `fern` \| `sprout` \| `grass` \| `blossom` |
| `sway` | `false` | wind phase across frames (needs `frames` ≥ 4) |
| `fill` | per-kind | `[r, g, b]` foliage / leaf color |
| `bark` | per-kind | `[r, g, b]` trunk (tree) / stem (plant) |
| `accent` | per-kind | `[r, g, b]` blossom petals / fruit |

`auto` lets the seed pick. Default palettes are colored (green foliage),
so `tint: shade` re-hues them via luminance like any other generator.

Canopies, trunk styles, plant forms and the age stages load from
`assets/vocab/flora.json`, with each stage's scaling numbers in `age_mods`
right beside its name, so a new stage arrives with its proportions attached.
See [Data-driven vocabularies](#data-driven-vocabularies).

## `face`

Emotion faces: 16 `mood` presets that combine eyes / mouth / brows /
extras into coherent expressions, plus per-part overrides that win over
the mood. Anatomy (head shape, eye and mouth scale) derives from the
item's **seed slot**, so all frames of an item are the same character.

With `count` ≥ 4 and blinkable eyes (`open`, `wide`, `wink`, `heart`)
exactly **one frame** per loop is the blink (eyes closed) — verified by
test. Showcase: `docs/showcase/face.png`.

| param | default | description |
|---|---|---|
| `mood` | `auto` | `auto` \| `neutral` \| `happy` \| `joy` \| `laugh` \| `sad` \| `cry` \| `angry` \| `scared` \| `surprised` \| `sleepy` \| `wink` \| `love` \| `confused` \| `worried` \| `determined` \| `dizzy` |
| `head` | `auto` | `auto` \| `round` \| `oval` \| `square` \| `wide` |
| `eyes` | `auto` | `auto` \| `open` \| `wide` \| `happy` \| `closed` \| `wink` \| `heart` \| `x` |
| `mouth` | `auto` | `auto` \| `flat` \| `smile` \| `grin` \| `open` \| `frown` \| `wavy` \| `cat` |
| `brows` | `auto` | `auto` \| `none` \| `flat` \| `angry` \| `sad` \| `raised` |
| `extras` | `auto` | `auto` \| `none` \| `blush` \| `sweat` \| `tears` \| `anger` |
| `fill` | `[245, 227, 201]` | `[r, g, b]` head tone |
| `outline` | `[70, 54, 48]` | `[r, g, b]` outline |
| `eye` | `[38, 34, 32]` | `[r, g, b]` pupils / closed lines |
| `eye_white` | `[255, 255, 255]` | `[r, g, b]` sclera |
| `accent` | `[244, 138, 150]` | `[r, g, b]` blush / heart eyes |
| `drop` | `[120, 190, 245]` | `[r, g, b]` sweat / tears |
| `mouth` | `[92, 54, 50]` | `[r, g, b]` mouth interior |
| `tongue` | `[240, 128, 128]` | `[r, g, b]` tongue |
| `anger` | `[222, 70, 58]` | `[r, g, b]` anger mark |

A part param (`eyes`, `mouth`, …) overrides the mood's choice for that
part only; `mood: auto` resolves to one of the 16 presets from the seed.
Example specs: `specs/flora.json`, `specs/face.json`.

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

# CLI reference

`sprout` is the console command (installed by `pip install sprout-toolkit`).
Every command accepts `--help`. Exit code is non-zero on any spec/validation
error, so all of them are CI-friendly.

## Commands

### `sprout init`

Writes a starter spec and generates its atlas in one step — pip-first
onboarding, no git clone needed. Re-runs never overwrite an existing edited
`starter.json`.

```bash
sprout init --out ./assets/starter          # spec + atlas
sprout init --out ./assets/starter --no-generate   # spec only
```

### `sprout generate <spec>`

Generates one spec: `atlas.png` + `manifest.json` + `index.ts` (plus optional
`.sksl`, per-tier `.sksl` files, `.tpsheet.json`, mip levels — see export
options below).

```bash
sprout generate specs/demo.json --out ./out
sprout generate specs/demo.json --seed 42        # override the spec's seed
sprout generate specs/demo.json --skip-existing   # no-op if output unchanged (CRC probe)

# Multi-resolution: one atlas per tier in <px>/ subdirs + a combined index.ts
sprout generate specs/demo.json --tiers 64,128,256 --out ./tiers
#   tiers/64/{atlas,manifest,index}.png|json|ts …  tiers/index.ts
#   -> atlasSources, pickTier (see docs/api.md)

# Single-resolution override: sister outputs without editing the spec
sprout generate specs/demo.json --frame-px 128 --out ./out-128

# Prebaked silhouette mask (black x alpha) alongside the atlas
sprout generate specs/demo.json --silhouette --out ./out
```

`--tiers` and `--frame-px` are mutually exclusive. `--silhouette` also works
with `batch` and with `--tiers` (one `silhouette.png` per tier).

### `sprout batch <dir>`

Generates every `*.json` spec found under a directory.

```bash
sprout batch specs/ --out ./out
```

### `sprout watch <dir>`

Regenerates when files under a directory change (Ctrl-C to exit). Writes are
atomic, so Metro/consumers never observe a half-written atlas — save a spec,
Metro hot-reloads the PNG.

```bash
sprout watch specs/ --out ./out --interval 1.0
```

### `sprout info <spec>`

Human-readable report of a resolved spec (seed, layout, items, animations) —
or `--json` for machine output.

```bash
sprout info specs/particles.json
sprout info --json specs/particles.json
```

### `sprout lint <spec>`

Quality analysis: atlas padding waste, empty frames, and bundle budget —
the atlas must stay under `--max-atlas-mb` (default 16 MB uncompressed RGBA;
`0` disables). Use `--json` as a CI gate.

```bash
sprout lint specs/ui.json
sprout lint --json specs/ui.json
sprout lint --max-atlas-mb 8 specs/tint.json
```

### `sprout diversity <spec>`

Form coverage: which items render to the same sprite. Renders every item
and compares the alpha silhouette on a 16×16 grid; items differing by
fewer than 12 of 256 cells are the same *form* — a coverage gap, since two
species that look identical need a new form or different params. Exits 1
on collision (CI gate); `--no-fail` reports without failing.

```bash
sprout diversity specs/catalog.json
sprout diversity --json specs/catalog.json
sprout diversity --no-fail specs/catalog.json
```

Generic: no generator knowledge, works for any catalog.

### `sprout diff <a> <b>`

Compares two specs, or two already-generated output directories (CRC +
manifest comparison).

```bash
sprout diff specs/props.json specs/ui.json
sprout diff --json ./out/a ./out/b
```

### `sprout validate <spec>`

Schema + plugin validation only (no rendering). Fast pre-commit check.

```bash
sprout validate specs/demo.json

# Coverage: fail (exit 1) if any catalog id has no frame — CI check.
sprout validate specs/catalog.json --coverage catalog.ts --field key
sprout validate specs/catalog.json --coverage catalog.ts --field key --map mapping.json
```

`--map` is optional; its `skip` ids are excluded from the expected set.

Validating also checks each item's `params` against the keys its
generator actually reads, so a typo in a mapping is reported before it
reaches the atlas.

### `sprout catalog <file>`

Codegen: emit a spec from a catalog file (`.json` list, or a `.ts`/`.js`
list of flat object literals) + an external `mapping.json`. The toolkit
has no domain knowledge — every set/id rule lives in your mapping.

```bash
sprout catalog catalog.ts --field key --map mapping.json --out specs/catalog.json
sprout catalog items.json --field id --generator props --seed 7
```

`mapping.json` (your side of the fence):

```json
{
  "sets": {
    "pets": { "generator": "critter", "frames": 4,
              "params": { "archetype": "quadruped" } },
    "glyphs": { "generator": "font" }
  },
  "ids": {
    "coin": { "generator": "props",
              "params": { "kind": "treasure", "form": "coin" } }
  },
  "default": { "generator": "props" },
  "skip": ["hand-drawn-id"]
}
```

Resolution per record: `ids[id]` > `sets[record.set]` > `default` >
error. `--generator` is the fallback when no `--map` is given.
`--set-field` selects the record field carrying the set name
(default `set`). Item ids are always the extracted field values.

### `sprout import <dir>`

Pack a directory of loose PNG frames (top-level `*.png` only) into an
atlas + manifest + `index.ts` — the fallback path for hand-drawn or
external art (gesture sprites, scanned art) instead of procgen.

```bash
sprout import ./frames/ --out ./assets/gestures --cols 2
sprout import ./frames/ -o ./out --name my_atlas --seed 7
```

- Frames must all share **one size** (the error lists what it found).
- Frame ids are the file stems, sorted alphabetically; ids may contain
  `A-Z a-z 0-9 _ -` only. Non-PNG files are ignored, broken PNGs fail.
- `--cols` (default 8) is the sheet grid width; the sheet grows by rows.
- `--name` defaults to `<dir>_atlas`; `--seed` is informational (recorded
  in the manifest, no RNG involved).

## Export options (`generate` / `batch`)

```bash
# PNG8 (indexed palette, lighter atlas) or PNG24 (no alpha)
sprout generate specs/ui.json --png-mode png8
sprout generate specs/autotile.json --png-mode png24   # only if no transparency

# Also emit <name>.tpsheet.json (TexturePacker JSON Hash format)
sprout generate specs/props.json --texturepacker

# Chain of atlas mip levels (@0.5x, @0.25x, @0.125x by default)
sprout generate specs/particles.json --mipmaps
sprout generate specs/particles.json --mipmaps --mipmap-levels 2
```

`--png-mode` defaults to `rgba` (no change):

| mode | effect | use when |
|---|---|---|
| `rgba` | no change | default |
| `png8` | quantize to 256 colors, alpha preserved per palette entry | limited/pixel-art palettes |
| `png24` | drops alpha entirely | atlas with no real transparency (e.g. `terrain`) |

`--texturepacker` and `--mipmaps` are opt-in and don't affect
`manifest.json`/`index.ts`, except that `--mipmaps` adds the `mipmaps.levels`
block to the manifest.

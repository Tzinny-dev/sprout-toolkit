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
`.sksl`, `.tpsheet.json`, mip levels — see export options below).

```bash
sprout generate specs/demo.json --out ./out
sprout generate specs/demo.json --seed 42        # override the spec's seed
sprout generate specs/demo.json --skip-existing   # no-op if output unchanged (CRC probe)
```

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

Quality analysis: atlas padding waste and empty frames. Use `--json` as a CI
gate.

```bash
sprout lint specs/ui.json
sprout lint --json specs/ui.json
```

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
```

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

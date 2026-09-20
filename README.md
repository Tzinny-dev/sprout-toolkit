# sprout-toolkit

**SPROUT** — Skia Procedural Rendering & Optimization Unified Toolkit

> Grow your 2D assets procedurally.

Sprout is an open-source toolkit for **deterministic procedural 2D asset generation**
targeting [Expo](https://expo.dev) + [`react-native-skia`](https://github.com/Shopify/react-native-skia).
It generates atlases, tilemaps, autotiles, bitmap fonts and SkSL shaders from JSON specs.

---

## Architecture

```
sprout/
├── sprout/                     # Python package
│   ├── __init__.py             #   __version__
│   ├── cli.py                  #   CLI (Typer): generate, batch, watch, info, lint, diff, validate
│   ├── exporter.py             #   Spritesheet packing, manifest.json, index.ts
│   ├── spec.py                 #   Load/validate JSON specs (schema v0)
│   ├── autotile.py             #   8-bit masks, 16/47 lookup
│   ├── sksl.py                 #   Runtime SkSL shaders (FBM value-noise)
│   ├── assets/fonts/           #   Bundled font (ships in the wheel)
│   └── generators/             #   Generation plugins
│       ├── base.py             #     FrameData + Generator (contract)
│       ├── terrain.py          #     Seamless tiles + autotile
│       ├── props.py            #     Static objects (5 kinds, anchor points)
│       ├── particles.py        #     Animated bursts with easing
│       ├── ui.py                #     Button, slider, 9-patch panel
│       ├── font.py              #     Bitmap font from TTF (one glyph per frame)
│       └── blob_walk.py        #     8-frame walk cycle
├── specs/                      # Example specs (one per generator)
├── tests/                      # 142 tests (determinism, autotile, SkSL, generators, CLI)
├── LICENSE                     # MIT
└── pyproject.toml
```

## Features

| Feature | Description |
|---|---|
| **Deterministic procgen** | Numeric seeds → reproducible assets (testable in CI). |
| **8-bit auto-tile** | 8-bit autotile mask (N/E/S/W + diagonals), 16 or 47 variants. |
| **Bitmap fonts from TTF** | Glyph atlas with advance metrics, ready for text layout. |
| **Runtime SkSL shaders** | Generated Skia shaders (FBM value-noise, tileable), no bundle weight added. |
| **Spec introspection** | `sprout info`/`sprout lint`/`sprout diff` to inspect, validate quality, and compare builds. |
| **Flexible export** | PNG8/PNG24, TexturePacker format, atlas mipmaps — all opt-in. |

## Installation

```bash
pip install sprout-toolkit
# or for development:
git clone https://github.com/Tzinny-dev/sprout-toolkit
cd sprout-toolkit
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
```

The installed command is `sprout` (not `sprout-toolkit` — that's just the PyPI distribution name).

## Quick start

### Generate assets

```bash
# Generate every asset defined under specs/
sprout batch specs/ --out ./out

# Generate a specific spec
sprout generate specs/demo.json --out ./out

# Watch mode: regenerates when files under specs/ change (Ctrl-C to exit)
sprout watch specs/ --out ./out --interval 1.0

# Inspect a spec (human report or JSON)
sprout info specs/particles.json
sprout info --json specs/particles.json

# Analyze spec quality: atlas padding + empty frames
sprout lint specs/ui.json
sprout lint --json specs/ui.json

# Generate a bitmap font atlas (printable ASCII, bundled font)
sprout generate specs/font.json --out ./out

# Compare two specs, or two already-generated output directories
sprout diff specs/props.json specs/ui.json
sprout diff --json ./out/a ./out/b

# Validate a spec
sprout validate specs/demo.json
```

### Export options (`generate` / `batch`)

```bash
# PNG8 (indexed palette, lighter atlas) or PNG24 (no alpha)
sprout generate specs/ui.json --png-mode png8
sprout generate specs/autotile.json --png-mode png24   # only if the atlas has no transparency

# In addition to manifest.json, emit <name>.tpsheet.json (TexturePacker JSON Hash format)
sprout generate specs/props.json --texturepacker

# Chain of atlas mip levels (@0.5x, @0.25x, @0.125x by default)
sprout generate specs/particles.json --mipmaps
sprout generate specs/particles.json --mipmaps --mipmap-levels 2
```

`--png-mode` defaults to `rgba` (no change). `png8` quantizes to 256 colors
while preserving the alpha channel (ideal for pixel-art-style limited
palettes); `png24` drops alpha entirely — only use it on atlases with no
real transparency (e.g. `terrain`). `--texturepacker`/`--mipmaps` are
opt-in and don't affect `manifest.json`/`index.ts`, except that `--mipmaps`
adds the `mipmaps.levels` block to the manifest.

### Available generators

| `generator` | Description | Params |
|-------------|-------------|--------|
| `terrain` | Seamless noise tiles + 16/47 autotile | `contrast`, `lift`, `cells`, `octaves`, `bevel`, `autotile` |
| `blob_walk` | 8-frame walk cycle (hero blob) | colors (`body`, `outline`, `belly`, ...) |
| `props` | Static objects: `rock`, `bush`, `chest`, `mushroom`, `flower` — each frame includes an anchor point (`frames[].anchor` in the manifest, computed from the real alpha bbox) | `kind`, `fill`, `outline` |
| `particles` | Animated bursts: `spark`, `smoke`, `dust`, `bubble` | `kind`, `particles`, `core`, `trail` |
| `ui` | Interface: `button` (normal/hover/pressed states), `slider` (progress + knob), `panel` (9-patch, `frames=9`) | `kind`, `fill`, `outline`, `accent` |
| `font` | Bitmap font from TTF, one glyph per frame (`frames` = `len(chars)`) | `chars`, `font_path`, `size`, `fill` |

Example spec using `props`:

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

## Development

```bash
pip install -e ".[test]"
pytest -q
```

CI (`.github/workflows/tests.yml`) runs the full suite on every push/PR,
across Python 3.10–3.13.
Publishing to PyPI is manual (`.github/workflows/publish.yml`, trusted
publishing via OIDC) — see [CHANGELOG](CHANGELOG.md).

## Credits

- `typer` + `Pillow` — CLI and image generation
- **DejaVu Fonts** (`DejaVuSansMono-Bold.ttf`, bundled in `sprout/assets/fonts/`) —
  Bitstream Vera license, see `sprout/assets/fonts/DejaVuSansMono-Bold.LICENSE.txt`

## License

MIT — see [LICENSE](LICENSE).

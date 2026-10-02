# Changelog

All notable changes to `sprout-toolkit` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).


## [Unreleased]

### Added

- **`sprout generate --supersample <1..8>`**: render each frame at
  `framePx × N` and box-filter the blocks back down to the same `framePx`.
  PIL's primitives are aliased, so every curve in the toolkit stair-steps —
  and raising `framePx` does not help, because the specs sample with
  `nearest` and point sampling drops the extra pixels rather than averaging
  them. Measured on `critter`: at N=1 zero pixels have a partial alpha and
  the frame holds 8 colours; at N=4, 5.2% of pixels are antialiased edges
  and it holds 562. So `nearest` plus a bigger source is the same atlas with
  more memory spent, and this is the flag that actually changes pixels.

  The output is logically untouched — `framePx`, `atlasW`/`atlasH` and every
  record's `x`/`y`/`w`/`h` are the same, and anchors and font advances, which
  generators report in frame pixels, are divided back down. `N=1` is the
  default and writes the exact bytes an unflagged `generate` would (all 13
  specs still byte-identical). No premultiplication is needed: Pillow
  premultiplies alpha while resampling, so the reduced sheet keeps its edge
  colour instead of averaging in the `(0, 0, 0, 0)` background — verified by
  filling transparent pixels red, green and white and getting the same
  result. N=4 is the useful setting (5.2% vs 3.4% at N=2 and 5.9% at N=8) for
  16x the *transient* memory; the real cost is PNG size, 216 KB to 416 KB
  across the 13 bundled specs. The 8x cap bounds a squared factor, not a
  recommendation. Tests: `test_supersample.py` (12).
- **`layout.supersample`**: the same setting as a spec field, so the smoothing
  decision travels with the spec instead of depending on whoever runs the
  command remembering a number. The 13 bundled specs and the `sprout init`
  template now ask for 4. `--supersample` becomes an *override* of the field
  rather than a default, so `sprout generate specs/critter.json` produces the
  smoothed atlas and `--supersample 1` still produces the old aliased bytes --
  verified: all 13 specs are byte-identical to their pre-flag output with
  `--supersample 1`. `render_items`/`build_sheet`/`build_font_map` default to
  the field too, so a library caller gets what the CLI would. Two consequences
  worth knowing: the test suite goes 13s -> 140s, because 4x means 16x the
  pixels to draw (transient memory, not a bigger atlas), and `sprout init`'s
  starter atlas changes, so its determinism pin moved. Tests:
  `test_supersample.py` (19).
- **`batch --out` writes one directory per spec**: it reported `13/13 specs ok`
  and left a *single* atlas, because all 13 bundled specs use
  `files.atlas: "atlas.png"` and every one of them wrote into the shared
  directory. The other 12 were overwritten and nothing said so. Each spec now
  lands in `<out>/<spec name>/`, and two specs sharing a `name` are refused up
  front (exit 1, nothing written) instead of colliding. Without `--out` each
  atlas still goes next to its own spec, where there was never a conflict.
  **Breaking**: this changes the `--out` layout, so scripts that read
  `<out>/atlas.png` need `<out>/<spec name>/atlas.png`. A setup that pointed at
  two differently-named atlases in one shared directory now gets one
  subdirectory per spec. `generate --out` is unaffected: it still writes a
  single flat directory, so the single-atlas case never moved.
- **`meta.provenance.supersample`** in the manifest: the factor actually used,
  including when `--supersample` overrode the spec. Recording it in `provenance`
  and not `units` because `units` is the contract for drawing the atlas and this
  does not change it -- but it does change the bytes, so a regenerated atlas
  that differs is now explainable from the manifest alone. The emitted
  `ManifestProvenance` type gained the field (optional, so the demo typechecks
  against a manifest written before this). Tests: `test_supersample.py` (24).
- **`sprout diversity <spec>`**: measure form coverage — which items share
  the same form. Groups items by generator, frame count, autotile and
  structural params, dropping palettes, colour literals and the `tint`
  declaration, so items differing only in colour count as one form
  recoloured. `--json` for machine output, `--no-fail` to report without
  exiting non-zero (default exits 1 on collision, for CI). Generic: no
  generator knowledge, works for any catalog. Tests: `test_diversity.py`
  (34).
- **Data-driven vocabularies**: `props`, `face`, `critter` and `flora` load
  their word lists from `assets/vocab/*.json` instead of hardcoding them, so
  a consumer can extend the toolkit's vocabulary without forking it.
  `SPROUT_VOCAB_DIR` points at a directory of same-named JSON files that
  deep-merge over the packaged defaults (lists replace, dicts merge
  recursively). Colors normalize from JSON `[r,g,b]` to the tuples PIL
  requires. Each generator moves the tables its options only mean something
  with: `critter` ships the per-archetype `auto` pick table and `flora` the
  per-age `age_mods` numbers, so extending a vocabulary cannot leave a value
  the renderer has no branch for. Purely a data move — all 13 bundled specs
  generate byte-identical atlases. Tests: `test_vocab.py` (23).
- **`face.params.mouth` resolved**: `mouth` named a shape in `MOUTHS` *and* a
  colour role in `DEFAULTS`, the only param where those collide, and the shape
  reading won — so `{"mouth": [200, 60, 60]}` was rejected with `invalid
  face.mouth`, and a colour role the docs listed was unreachable from any spec.
  The value type now settles it: a string picks the shape, a `[r, g, b]` list
  recolours the mouth and leaves the shape on the mood. It also honours the
  colour on the five line-shaped mouths (`flat`/`smile`/`frown`/`wavy`/`cat`),
  which have always been inked in the `eye` colour so a face reads as one
  drawing — accepting the colour without applying it there would mean a spec
  that validates and then draws no change at all. Default output unchanged:
  `face.json` still generates a byte-identical atlas, as do all 13 specs. Junk
  in `mouth` (`"grill"`, `7`, a 2- or 4-int list) is still rejected, so the
  disambiguation is not a hole in validation. Tests: `test_face.py`
  (123 → 149).
- **Unknown-param validation**: every built-in generator declares the
  `item.params` keys it reads (`Generator.PARAMS`), and the spec loader
  rejects anything else. A typo in a hand-written `mapping.json` — the
  kind that used to render a plausible-but-wrong sprite — now fails with
  the offending key and the known ones: `item 'frutilla': unknown param(s)
  for 'props': 'forma' (known: accent, autotile, fill, form, kind,
  outline, palette)`. Purely additive: `palette`/`autotile` stay
  framework-level, palette-expanded color roles are not attributed to the
  author, and all 13 bundled specs still generate byte-identical atlases.
  Plug-ins that predate the attribute (`PARAMS = None`) skip the check.
  Tests: `test_param_validation.py` (23).
- **Third-party generators via entry points**: a distribution can now add
  generators to the registry without forking the toolkit, by advertising
  them under the `sprout.generators` group:
  `[project.entry-points."sprout.generators"] vehicle = "pkg.mod:Vehicle"`.
  Discovery is forgiving — a plug-in that fails to import, points at a
  missing attribute, or exposes a non-`Generator` is skipped instead of
  breaking the built-ins. Built-in ids always win a collision, so
  installing a plug-in can never change the output of an existing spec.
  `sprout info` lists the active plug-in ids; `BUILTIN_GENERATORS` and
  `plugin_generator_ids()` expose the split. Tests: `test_plugins.py` (21).

### Breaking changes

- **`batch --out` layout is now one directory per spec** (`<out>/<spec name>/`).
  See the entry above: the old flat layout silently discarded every atlas but
  the last, which is a worse failure than the migration this asks for.
  Consumers using `batch --out` with a shared directory need to update their
  read paths; `generate --out` is unaffected.

## [0.3.0] — 2026-09-27

First phased release of the 0.3 line (see §6.3 of the project plan):
everything below is additive — no existing spec stopped validating. The
only on-disk delta for consumers is manifests gaining `schemaVersion`
(and the toolkit version string in generated headers / `meta.generator`).

### Added

- **`sprout import <dir>`**: pack a directory of loose, uniformly-sized
  PNGs (top-level `*.png`; ids = sorted stems) into atlas + `manifest.json`
  + `index.ts` — the fallback path for hand-drawn/external art (gesture
  sprites, scanned sprites) instead of procgen. Errors name the offending
  frame, id or size mismatch. Tests: `test_import.py` (+8).
- **npm wrapper (`sprout-toolkit` on npm, `npm/`)**: `npx sprout` spawns
  `python3 -m sprout` and enforces a **strict version pin** — it refuses
  to run when the installed CLI version differs from the wrapper's own,
  printing the exact `pip install "sprout-toolkit==<version>"` command
  (wrapper nuevo nunca corre con CLI viejo). `SPROUT_PYTHON` points it at
  another interpreter. `tests/test_fase8.py` asserts the three version
  sources (pyproject, `sprout.__version__`, npm `package.json`) stay equal.
- **Manifest `schemaVersion: 1`**: integer schema revision next to
  `schema: "sprout/manifest@0"` (typed `schemaVersion: number` in the
  generated `Manifest` interface). Breaking manifest changes bump it;
  consumers must refuse a revision they don't know instead of misreading
  fields. Policy documented in `docs/api.md`.
- **Pipeline CI (`.github/workflows/ci.yml`)**: lints every spec,
  generates every spec end-to-end, smoke-tests the npm wrapper's version
  pin, and runs the `validate --coverage` example when a consumer's
  `catalog.ts` + `mapping.json` sit at the repo root. Unit matrix + wheel
  smoke stay in `tests.yml`.
- **`python3 -m sprout`** entry point (`sprout/__main__.py`) — the module
  invocation the npm bin spawns.

- **Tier effect shaders (spec `tiers` block)**: named overlay templates
  beyond the FBM terrain shader — `holographic`, `neon`, `legend-glow` and
  the trivial `invisible` (alpha 0). Each entry writes `<name>.<tier>.sksl`
  + a manifest `tiers` block (seed-derived uniforms) + `TIER_SHADERS` /
  `tierUniforms(name, time)` in `index.ts`. String shorthand
  (`"holo": "holographic"`) or `{template, speed, glow}`; the mapping is
  yours — the toolkit stays domain-free. Tests: `test_sksl.py` (+13).
- **Multi-escala (`--tiers`)**: `sprout generate <spec> --tiers 64,128,256`
  emits one full output per resolution in `<px>/` subdirs plus a combined
  `index.ts` (`atlasSources`, `TIERS`, `pickTier`, base-tier re-export).
  Sister resolutions no longer need sister spec files — one spec drives
  them all. Companion `--frame-px` overrides `layout.framePx` for a single
  output. `sample: linear` documented for displaying a smaller tier larger.
- **Silhouettes**: prebaked mask via `generate`/`batch --silhouette`
  (`silhouette.png` = black × original alpha, `files.silhouette` in the
  manifest, `SILHOUETTE_SOURCE` + `useSilhouetteImage()` in `index.ts`);
  runtime stays primary — new `useSilhouetteSprites(specs)` hook returns
  `useAtlasSprites` + black×alpha colors in one call, and
  `spriteLayout(id, cx, cy, size)` centers a frame in a box/circle.
  Tests: `tests/test_multiscale.py` (14).
- **`sprout catalog <file> --field <name> --map mapping.json`**: codegen
  from any catalog (`.json` list or flat-object `.ts` list) — extracts
  ids and materializes a spec by applying an external mapping
  (`sets`/`ids`/`default` rules + `skip` list). The toolkit stays
  domain-free: the mapping lives on the consumer's side.
  Companion flag **`sprout validate --coverage`**: fails (exit 1) when a
  catalog id has no frame — the CI coverage check. Tests: `test_catalog.py`.
- **`props` v3 object grammar**: the generator gains a `form` param and
  seven new kinds covering flavor/thing catalog sets — `fruit` (5),
  `sweet` (5), `potion` (3), `treasure` (4), `tool` (5), `paper` (3),
  `container` (2) = 27 forms; `form: "auto"` picks one per variant from
  the seed, explicit `form` pins it (classic v1 kinds stay formless and
  byte-stable). v3 kinds derive their outline from `fill` via the shared
  rule and accept an `accent` override. Spec: `specs/objects.json`,
  showcase: `docs/showcase/objects.png`.
- **Bundled-font symbol coverage test**: a curated BMP symbol set
  (♥★☆☀✂⚑⚙✓✗⚠♪❤…) is asserted to render as real glyphs in DejaVu Sans
  Mono Bold (mask compared against `.notdef`). Supplementary-plane
  codepoints (emoji, ⭐❌➿) fall back to `sprout import`.
- **`flora` generator**: trees and forest-floor plants. Trees combine a
  tapered trunk (`straight` / `gnarled` = lean + kink) with three canopy
  shapes (`round`, `columnar`, `conifer`) via a union-outline pass;
  plants are undergrowth forms (`fern`, `sprout`, `grass`, `blossom`)
  picked by seed. Anatomy derives from the item's seed slot; optional
  `sway` animates the canopy / stem across frames (pivot at the ground).
  Spec: `specs/flora.json`, showcase: `docs/showcase/flora.png` +
  `flora_sway.gif`.
- **`face` generator**: emotion faces — 16 `mood` presets
  (`neutral` … `dizzy`) combining eyes / mouth / brows / extras, with
  per-part overrides that win over the mood and four head shapes.
  One-frame blink per loop (≥ 4 frames, blinkable eyes), verified by
  test. Spec: `specs/face.json`, showcase: `docs/showcase/face.png`.
- **`critter` generator**: parametric animals — `quadruped`, `bird`,
  `fish`, `reptile`, `bug` (top view) with composable parts
  (`ears`/`snout`/`tail`/`legs`/`wings`, `facing`, color overrides).
  Anatomy derives from the item's seed slot, so all frames of an item are
  the same species; frames animate a breathing idle + a one-frame blink.
  Neutral tint-ready palette. Spec: `specs/critter.json`,
  showcase: `docs/showcase/critter.png` + `critter_idle.gif`.
- **Runtime tint (color variants)**: specs can declare a `colors` palette
  (`[{key, hex}]`) and mark items as `tint: shade | full`. The manifest gains
  a `tint` block and `index.ts` exports `TINTS`, `TINT_MODES`,
  `colorMatrixFor`, `hexToRgb`, `tintPaint`, `tintColor(s)`,
  `silhouettePaint/Colors` and `SILHOUETTE_MATRIX` — one sprite per item
  recolored at runtime (`<Atlas colors>` + `colorBlendMode="modulate"`, or a
  paint-level `Skia.ColorFilter.MakeMatrix`) instead of baking N copies.
  Spec: `specs/tint.json`.
- **Named palettes + outline rule** (`sprout/palettes.py`): `params.palette`
  (`earth`, `forest`, `ocean`, `candy`) fills unset color roles
  (`fill`/`accent`/`outline`); explicit `params.fill`/`outline` always win.
  Outline = `darken(fill, 0.55)`, width = `max(1, framePx // 32)`.
- `sprout lint --max-atlas-mb` (default 16 MB): warns when the uncompressed
  RGBA atlas exceeds the bundle budget (`check: atlas_size`, `0` disables).
- `sprout diff` now compares item `tint` and the spec-level `colors` palette;
  output-dir diff also covers the `tint` manifest block.
- `index.ts` now exports a typed `GENERATOR` (`{ name, version }`) plus the
  `ManifestMeta` / `GeneratorMeta` interfaces — `manifest.meta` is typed
  instead of `unknown`. Includes a manifest provenance test.
- Wheel smoke test in CI (`smoke-test-wheel` job): build → `twine check` →
  install the wheel in a clean venv → `sprout --version` / `sprout info`.
- Release checklist + emergency rollback playbook in the README.
- Reference docs: spec schema, generators (params + defaults), CLI commands
  and export options, and the manifest/index.ts API (`docs/*.md`).
- `site/`: React + Vite landing page with the full docs section, auto-deployed
  to GitHub Pages (`.github/workflows/pages.yml`).

### Changed

- Pillow dependency pinned to `>=10,<13` — the suite is validated against
  12.3.0; Pillow 14 (2027) deprecates `Image.getdata` (tests only).

## [0.2.1] — 2026-09-20

### Fixed

- Atomic artifact writes (`temp file + os.replace`): readers — `sprout watch`
  consumers, Metro, file pollers — never observe half-written `atlas.png` /
  `manifest.json` / `index.ts`. Found via a CI flake where a test read the
  atlas mid-write (CRC 0).

### Changed

- README branding: `SPROUT` → `SPROUT TOOLKIT`.

## [0.2.0] — 2026-09-20

Pip-first onboarding: from `pip install` to sprites on screen in ~10 minutes,
with no git clone required.

### Added

- `sprout init --out ./assets/starter`: writes a starter spec and generates
  its atlas in one step (pip-first onboarding, no git clone needed). Reruns
  never overwrite an edited `starter.json` (`--no-generate` to skip the
  build).
- `specs/starter.json`: 8 walk frames + 4 prop frames (seed 7), backing the
  new 10-minute tutorial.
- `docs/starter-tutorial.md`: from `pip install` to sprites on screen in a
  fresh Expo app (SDK 57 + Skia 2.6.2), verified end-to-end (`tsc` clean +
  `expo export` bundles the generated atlas via Metro).

## [0.1.1] — 2026-09-20

First public release on PyPI (`sprout-toolkit`; install with
`pip install sprout-toolkit`, command stays `sprout`).

### Changed

- Translated the entire codebase to English: CLI help/output, docstrings,
  comments, error messages, and the error strings embedded in the generated
  TypeScript template. No identifiers, manifest keys, or spec params changed.
- Renamed the PyPI distribution from `sprout` to `sprout-toolkit` (the bare
  `sprout` name belongs to an unrelated package). Console script is still
  `sprout`.
- Completed package metadata: authors, README as long description,
  classifiers, keywords, and project URLs.

### Fixed

- Packaging: `LICENSE` included in the repo and the wheel ships the bundled
  font (`sprout/assets/fonts/`), so `sprout generate specs/font.json` works
  from a clean `pip install`.

### Added

- Standalone `README.md` for the published repo (docs previously lived only
  in the private parent monorepo).
- CI workflow running `pytest` on push/PR.

## [0.1.0] — 2026-09-19

Internal milestone: deterministic procedural 2D asset toolchain
(`terrain`/`blob_walk` generators, 16/47 autotile, SkSL runtime emitter)
plus the full growth-plan cycle:

- Generators: `props` (5 kinds, anchor point per frame), `particles`
  (4 animated burst kinds), `ui` (button/slider/9-patch panel), `font`
  (bitmap font from TTF with advance metrics).
- CLI: `generate`, `batch`, `watch`, `info`, `lint`, `diff`, `validate`.
- Export: spritesheet + `manifest.json` + `index.ts` (Atlas helpers,
  batch/imperative helpers, font glyph maps), opt-in PNG8/PNG24,
  TexturePacker JSON, atlas mipmaps.
- 142 tests (`pytest tests/ -q`).

[Unreleased]: https://github.com/Tzinny-dev/sprout-toolkit/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/Tzinny-dev/sprout-toolkit/releases/tag/v0.2.1
[0.2.0]: https://github.com/Tzinny-dev/sprout-toolkit/releases/tag/v0.2.0
[0.1.1]: https://github.com/Tzinny-dev/sprout-toolkit/releases/tag/v0.1.1
[0.1.0]: https://github.com/Tzinny-dev/sprout-toolkit/releases/tag/v0.1.0

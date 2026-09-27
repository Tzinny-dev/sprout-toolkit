# Changelog

All notable changes to `sprout-toolkit` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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

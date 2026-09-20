# Changelog

All notable changes to `sprout-toolkit` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/Tzinny-dev/sprout-toolkit/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/Tzinny-dev/sprout-toolkit/releases/tag/v0.1.1
[0.1.0]: https://github.com/Tzinny-dev/sprout-toolkit/releases/tag/v0.1.0

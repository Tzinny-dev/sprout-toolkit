# sprout-toolkit (npm)

npm wrapper for the **sprout** Python CLI — deterministic procedural 2D
asset generation for Expo + react-native-skia. The `sprout` bin spawns
`python3 -m sprout` and enforces a **strict version pin**: the wrapper's
version must equal the installed CLI's version.

## Requirements

- Node 18+
- Python 3.10+ available as `python3` (or set `SPROUT_PYTHON`)
- The pinned CLI: `python3 -m pip install "sprout-toolkit==0.4.0"`

## Usage

```bash
npm install --save-dev sprout-toolkit

npx sprout --version                 # verifies the pin
npx sprout generate specs/demo.json --out ./assets/procgen
npx sprout batch specs/ --out ./assets/out    # -> assets/out/<spec name>/
```

Typical consumer wiring:

```json
{
  "scripts": {
    "assets:gen": "sprout batch specs/ --out ./assets/out"
  }
}
```

Note the `--out` layout: `batch` gives every spec its own directory named after
the spec's `name`, so one `--out` can hold a whole set of atlases that do not
share a filename. That is not cosmetic — every bundled spec calls its atlas
`atlas.png`, so writing them all into a single shared directory left one file
holding whichever spec ran last while `batch` still reported `13/13 specs ok`.
Point `generate` at a single directory when you want the atlas flat.

If Python or the CLI is missing, the bin exits with the exact
`pip install "sprout-toolkit==<version>"` command to run.

## Version policy

`package.json` version == `sprout-toolkit` (PyPI) version == `sprout --version`.
Both channels are released in lockstep; the wrapper refuses to run a CLI
whose version differs from its own.

MIT

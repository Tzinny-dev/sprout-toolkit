# sprout-toolkit (npm)

npm wrapper for the **sprout** Python CLI — deterministic procedural 2D
asset generation for Expo + react-native-skia. The `sprout` bin spawns
`python3 -m sprout` and enforces a **strict version pin**: the wrapper's
version must equal the installed CLI's version.

## Requirements

- Node 18+
- Python 3.10+ available as `python3` (or set `SPROUT_PYTHON`)
- The pinned CLI: `python3 -m pip install "sprout-toolkit==0.3.0"`

## Usage

```bash
npm install --save-dev sprout-toolkit

npx sprout --version                 # verifies the pin
npx sprout generate specs/demo.json --out ./assets/procgen
npx sprout batch specs/ --out ./assets/procgen
```

Typical consumer wiring:

```json
{
  "scripts": {
    "assets:gen": "sprout batch specs/ --out ./assets/procgen"
  }
}
```

If Python or the CLI is missing, the bin exits with the exact
`pip install "sprout-toolkit==<version>"` command to run.

## Version policy

`package.json` version == `sprout-toolkit` (PyPI) version == `sprout --version`.
Both channels are released in lockstep; the wrapper refuses to run a CLI
whose version differs from its own.

MIT

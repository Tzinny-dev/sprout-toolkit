# sprout-toolkit

**SPROUT** — Skia Procedural Rendering & Optimization Unified Toolkit

> Grow your 2D assets procedurally.

Sprout es un toolkit de código abierto para **generación procedural determinista de assets 2D**
destinados a [Expo](https://expo.dev) + [`react-native-skia`](https://github.com/Shopify/react-native-skia).
Genera atlases, mapas de tiles, autotiles, bitmap fonts y shaders SkSL a partir de specs JSON.

---

## Arquitectura

```
sprout/
├── sprout/                     # Paquete Python
│   ├── __init__.py             #   __version__
│   ├── cli.py                  #   CLI (Typer): generate, batch, watch, info, lint, diff, validate
│   ├── exporter.py             #   Spritesheet packing, manifest.json, index.ts
│   ├── spec.py                 #   Carga/validación de specs JSON (schema v0)
│   ├── autotile.py             #   Máscaras 8-bit, lookup 16/47
│   ├── sksl.py                 #   Shaders SkSL runtime (FBM value-noise)
│   ├── assets/fonts/           #   Fuente empaquetada (viaja en el wheel)
│   └── generators/             #   Plugins de generación
│       ├── base.py             #     FrameData + Generator (contrato)
│       ├── terrain.py          #     Tiles seamless + autotile
│       ├── props.py            #     Objetos estáticos (5 kinds, anchor points)
│       ├── particles.py        #     Bursts animados con easing
│       ├── ui.py                #     Botón, slider, panel 9-patch
│       ├── font.py              #     Bitmap font desde TTF (un glifo por frame)
│       └── blob_walk.py        #     8-frame walk cycle
├── specs/                      # Specs de ejemplo (uno por generador)
├── tests/                      # 142 tests (determinismo, autotile, SkSL, generadores, CLI)
├── LICENSE                     # MIT
└── pyproject.toml
```

## Características

| Característica | Descripción |
|---|---|
| **Procgen determinista** | Seeds numéricas → assets reproducibles (testeable en CI). |
| **Auto-tile 8-bit** | Máscara de autotile con 8 bits (N/E/S/W + diagonales), 16 o 47 variantes. |
| **Bitmap fonts desde TTF** | Atlas de glifos con métricas de avance, listo para layout de texto. |
| **Shaders SkSL runtime** | Shaders generados para Skia (FBM value-noise, tileable), sin engordar el bundle. |
| **Introspección de specs** | `sprout info`/`sprout lint`/`sprout diff` para inspeccionar, validar calidad y comparar builds. |
| **Exportación flexible** | PNG8/PNG24, formato TexturePacker, mipmaps del atlas — todo opt-in. |

## Instalación

```bash
pip install sprout-toolkit
# o en desarrollo:
git clone https://github.com/Tzinny-dev/sprout-toolkit
cd sprout-toolkit
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
```

El comando instalado es `sprout` (no `sprout-toolkit` — ese es solo el nombre de distribución en PyPI).

## Uso rápido

### Generar assets

```bash
# Generar todos los assets definidos en specs/
sprout batch specs/ --out ./out

# Generar un spec específico
sprout generate specs/demo.json --out ./out

# Modo watch: regenera al detectar cambios en specs/ (Ctrl-C para salir)
sprout watch specs/ --out ./out --interval 1.0

# Inspeccionar una spec (reporte humano o JSON)
sprout info specs/particles.json
sprout info --json specs/particles.json

# Analizar calidad de una spec: padding de atlas + frames vacíos
sprout lint specs/ui.json
sprout lint --json specs/ui.json

# Generar un atlas de bitmap font (ASCII imprimible, fuente empaquetada)
sprout generate specs/font.json --out ./out

# Comparar dos specs, o dos directorios de salida ya generados
sprout diff specs/props.json specs/ui.json
sprout diff --json ./out/a ./out/b

# Validar un spec
sprout validate specs/demo.json
```

### Opciones de exportación (`generate` / `batch`)

```bash
# PNG8 (paleta indexada, atlas más liviano) o PNG24 (sin alpha)
sprout generate specs/ui.json --png-mode png8
sprout generate specs/autotile.json --png-mode png24   # solo si el atlas no usa transparencia

# Además de manifest.json, emite <name>.tpsheet.json (formato TexturePacker JSON Hash)
sprout generate specs/props.json --texturepacker

# Cadena de mip levels del atlas (@0.5x, @0.25x, @0.125x por defecto)
sprout generate specs/particles.json --mipmaps
sprout generate specs/particles.json --mipmaps --mipmap-levels 2
```

`--png-mode` default es `rgba` (sin cambios). `png8` cuantiza a 256 colores
preservando el canal alpha (ideal para paletas acotadas tipo pixel-art);
`png24` descarta el alpha por completo — solo usarlo en atlases sin
transparencia real (p. ej. `terrain`). `--texturepacker`/`--mipmaps` son
opt-in y no afectan `manifest.json`/`index.ts`, salvo que `--mipmaps`
agrega el bloque `mipmaps.levels` al manifest.

### Generadores disponibles

| `generator` | Descripción | Params |
|-------------|-------------|--------|
| `terrain` | Tiles de ruido seamless + autotile 16/47 | `contrast`, `lift`, `cells`, `octaves`, `bevel`, `autotile` |
| `blob_walk` | Ciclo de caminata de 8 frames (hero blob) | colores (`body`, `outline`, `belly`, ...) |
| `props` | Objetos estáticos: `rock`, `bush`, `chest`, `mushroom`, `flower` — cada frame incluye un anchor point (`frames[].anchor` en el manifest, calculado desde el bbox alpha real) | `kind`, `fill`, `outline` |
| `particles` | Bursts animados: `spark`, `smoke`, `dust`, `bubble` | `kind`, `particles`, `core`, `trail` |
| `ui` | Interfaz: `button` (estados normal/hover/pressed), `slider` (progreso + knob), `panel` (9-patch, `frames=9`) | `kind`, `fill`, `outline`, `accent` |
| `font` | Bitmap font desde TTF, un glifo por frame (`frames` = `len(chars)`) | `chars`, `font_path`, `size`, `fill` |

Ejemplo de spec con `props`:

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

## Desarrollo

```bash
pip install -e ".[test]"
pytest -q
```

CI (`.github/workflows/tests.yml`) corre la suite completa en cada push/PR.

## Créditos

- `typer` + `Pillow` — CLI y generación de imágenes
- **DejaVu Fonts** (`DejaVuSansMono-Bold.ttf`, empaquetada en `sprout/assets/fonts/`) —
  licencia Bitstream Vera, ver `sprout/assets/fonts/DejaVuSansMono-Bold.LICENSE.txt`

## Licencia

MIT — ver [LICENSE](LICENSE).

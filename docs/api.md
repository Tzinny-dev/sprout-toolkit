# Outputs: `manifest.json` + `index.ts`

Every `sprout generate` / `sprout batch` emits three artifacts. This page
documents the contract of the two machine-readable ones.

| file | role |
|---|---|
| `atlas.png` | the spritesheet |
| `manifest.json` | machine-readable map: frame coords, anims, blocks |
| `index.ts` | typed module wired for `@shopify/react-native-skia` |

## `manifest.json`

```json
{
  "schema": "sprout/manifest@0",
  "name": "starter_atlas",
  "seed": 7,
  "kind": "atlas",
  "files": { "atlas": "atlas.png", "atlasW": 256, "atlasH": 192 },
  "units": { "tileLogical": 32, "framePx": 64, "sample": "nearest" },
  "frames": [
    { "id": "hero_00", "col": 0, "row": 0, "x": 0, "y": 0, "w": 64, "h": 64,
      "anchor": { "x": 32, "y": 61 } }
  ],
  "anim": { "walk": { "frames": ["hero_00", "..."], "fps": 8, "loop": true } },
  "tiles": { "ids": [] },
  "meta": {
    "provenance": { "spec": "starter.json", "git": "" },
    "generator": { "name": "sprout", "version": "0.2.1" }
  }
}
```

- **`frames[]`** — `id` is `<item>_<index>` (`hero_00`, `hero_01`, …).
  `anchor` appears **only on `props` frames** (ground-contact point in local
  frame pixels, from the real alpha bbox).
- **`anim`** — resolved frame-id lists per animation.
- **`tiles.ids`** — frame ids of `terrain` items (for tilemap rendering).
- **`meta.generator`** — which toolkit version produced the file: handy when
  debugging reproducibility across releases.
- **Optional blocks** (present only when generated):
  - `autotile` — `{ bitmask, items: { <id>: { size, mask: {mask: frameId} } } }`
  - `shader` — `{ file, uniforms }` when `runtime` is on
  - `font` — `{ items: { <id>: { ascent, descent, glyphs: { char: {id, advance} } } } }`
  - `mipmaps` — `{ levels: [{scale, file, w, h}] }` with `--mipmaps`
  - `tint` — `{ colors: [{key, hex}], items: { <id>: 'shade' | 'full' } }`
    when the spec declares `colors` or a tinted item

## `index.ts` exports

### Types

```ts
interface Frame { id; col; row; x; y; w; h; anchor?: { x; y } }
interface Anim  { frames: string[]; fps: number; loop: boolean }
interface SpriteSpec { id: string; x: number; y: number; scale?: number }
interface Manifest { schema; name; seed; …; tint?: TintBlock; meta: ManifestMeta }
interface ManifestMeta { provenance; generator: GeneratorMeta }
type TintMode = 'shade' | 'full';
interface TintColor { key: string; hex: string }
interface TintBlock { colors: TintColor[]; items: Record<string, TintMode> }
```

### Constants

| export | description |
|---|---|
| `manifest` | the parsed `manifest.json`, typed |
| `ATLAS_SOURCE` | static `require()` of the PNG (Metro/EAS-safe) |
| `SILHOUETTE_SOURCE` | static `require()` of the prebaked mask (`null` without `--silhouette`) |
| `frameScale` | `tileLogical / framePx` (e.g. `0.5`) |
| `tileFrames` | `Frame[]` of all `terrain` items |
| `AUTOTILE_BITS` | `N/NE/E/SE/S/SW/W/NW` bit flags |
| `GENERATOR` | `{ name, version }` of the producing toolkit |
| `sampleMode`, `atlasSampling` | Skia filter mode from `units.sample` |
| `SHADER_SKS`, `SHADER_DEFAULTS` | SkSL source + default uniforms (`null` when runtime off) |
| `TIER_SHADERS` | tier name → embedded SkSL source (empty without a `tiers` block) |
| `TINTS` | `Record<key, '#RRGGBB'>` from the spec's `colors` (empty without a tint block) |
| `TINT_MODES` | `Record<itemId, TintMode>` for tinted items |
| `SILHOUETTE_MATRIX` | 4×5 color matrix: black × original alpha |

### Lookup helpers

```ts
frameById(id: string): Frame            // throws on unknown id
framesFor(animId: string): Frame[]      // animation → frames
rectFor(frameId: string)                // {x,y,w,h} with half-texel inset (anti-bleed)
spriteLayout(id, cx, cy, size)           // SpriteSpec: center the frame's box in a size x size target
autotileFrame(mask: number, item?): Frame
canonicalMask(mask: number, size: 16 | 47): number
glyphFrame(char: string, item?): Frame
textSprites(text, origin, item?, scale?): SpriteSpec[]
shaderUniforms(time): Record<string, number | number[]>
tierUniforms(name, time?): Record<string, number>   // tier effects (spec `tiers` block)
```

### Runtime tint helpers

```ts
tintModeFor(itemId): TintMode | 'none'          // from manifest.tint.items
hexToRgb(hex): [number, number, number]         // '#RRGGBB' -> 0..1
colorMatrixFor(hex, mode?): number[]            // 4x5 Skia matrix ('shade' | 'full')
tintColor(key): SkColor                         // declared tint key -> SkColor
tintColors(specs, key): SkColor[]               // one color per sprite (same tint)
silhouetteColors(specs): SkColor[]              // black x alpha, per sprite
tintPaint(hex, mode?): SkPaint                  // paint with the tint color filter
silhouettePaint(): SkPaint                      // paint with SILHOUETTE_MATRIX
```

**Two ways to tint a batch:**

```tsx
// 1) One color for the whole batch — paint-level color filter.
//    'shade' keeps the sprite's luminance (correct on colored art).
const paint = tintPaint(TINTS.ember, 'shade');
<Atlas paint={paint} image={…} sprites={…} transforms={…} />

// 2) One color per sprite — native colors, modulate (texture x color).
//    Identical to 'shade' on tint-ready (neutral) art.
const colors = tintColors(specs, 'ember');
<Atlas colors={colors} colorBlendMode="modulate"
       image={…} sprites={…} transforms={…} />
```

**Hidden items (mode ciego)** — no extra atlas frames:

```tsx
const s = useSilhouetteSprites(specs);   // one call: sprites + black x alpha colors
<Atlas {...s} colors={s.colors} colorBlendMode="modulate" />
// or the lower-level pieces:
const colors = silhouetteColors(specs);  // batch path
const paint = silhouettePaint();         // paint path
```

Or point at the prebaked mask (`generate --silhouette`):
`useSilhouetteImage()` loads `SILHOUETTE_SOURCE` (`null` without the flag).

### Rendering hooks (react-native-skia)

```ts
useAtlasImage(): SkImage | undefined     // loads ATLAS_SOURCE
useSilhouetteImage(): SkImage | null     // loads SILHOUETTE_SOURCE (null without --silhouette)
useAtlasSprites(specs, scale?): { image, sprites, transforms, sampling }
useSilhouetteSprites(specs, scale?):     // useAtlasSprites + colors (black x alpha)
useAtlasGrid(ids, cols, origin?, tile?): same shape, laid out on a grid
useAtlasBatch(specs, extra?, scale?):    // imperative path: preallocated buffers
toSpecData(specs, scale?): SpriteSpecData     // flat tuples for worklets
inflateSpecData(data): { rects, xforms }      // pools without realloc
inflateInto(data): void                       // in-place refill (useAtlasBatch)
makeStaticAtlasPicture(data, image, dpr?): SkPicture  // one drawAtlas for N sprites
```

**Declarative vs batch:** `useAtlasSprites` is one `<Atlas>` per render —
simple, ideal for UI and small scenes. `useAtlasBatch` +
`makeStaticAtlasPicture` preallocate rect/RSXform buffers and can bake a whole
tilemap into a single `SkPicture` (one `drawAtlas`) — validated on a Pixel 8
against the declarative path (per-tile diff 0.92 vs 0.95, both acceptable).

## Resolution tiers (`--tiers 64,128,256`)

`sprout generate <spec> --tiers 64,128,256` writes one full output per
resolution — `<out>/<px>/{atlas,manifest,index}` — plus a combined
`<out>/index.ts` that routes between them:

```ts
export type Tier = 64 | 128 | 256;
export const TIERS: readonly Tier[];
export const atlasSources: Record<Tier, { atlas: number; manifest: Manifest }>;
export function pickTier(px: number): Tier;  // smallest tier >= px (else largest)
```

The base (smallest) tier's API is re-exported, so a single import gives
both the router and the helpers:

```tsx
import { atlasSources, pickTier } from './assets/tiers';

const tier = pickTier(200);                    // -> 256
const { atlas, manifest } = atlasSources[tier];
```

One spec drives every tier (`--tiers` overrides `layout.framePx` per
output). Pair a smaller tier with `sample: "linear"` when you display it
larger than its native pixels.

## Minimal usage

```tsx
import { Atlas, Canvas } from '@shopify/react-native-skia';
import { framesFor, useAtlasSprites } from './assets/starter';

function Hero() {
  const sprites = useAtlasSprites(
    framesFor('walk').map((f, i) => ({ id: f.id, x: 24 + i * 40, y: 300 })),
  );
  return (
    <Atlas image={sprites.image} sprites={sprites.sprites}
           transforms={sprites.transforms} sampling={sprites.sampling} />
  );
}
```

End-to-end walkthrough: [10-minute quickstart](/docs/quickstart).

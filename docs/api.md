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

## `index.ts` exports

### Types

```ts
interface Frame { id; col; row; x; y; w; h; anchor?: { x; y } }
interface Anim  { frames: string[]; fps: number; loop: boolean }
interface SpriteSpec { id: string; x: number; y: number; scale?: number }
interface Manifest { schema; name; seed; …; meta: ManifestMeta }
interface ManifestMeta { provenance; generator: GeneratorMeta }
```

### Constants

| export | description |
|---|---|
| `manifest` | the parsed `manifest.json`, typed |
| `ATLAS_SOURCE` | static `require()` of the PNG (Metro/EAS-safe) |
| `frameScale` | `tileLogical / framePx` (e.g. `0.5`) |
| `tileFrames` | `Frame[]` of all `terrain` items |
| `AUTOTILE_BITS` | `N/NE/E/SE/S/SW/W/NW` bit flags |
| `GENERATOR` | `{ name, version }` of the producing toolkit |
| `sampleMode`, `atlasSampling` | Skia filter mode from `units.sample` |
| `SHADER_SKS`, `SHADER_DEFAULTS` | SkSL source + default uniforms (`null` when runtime off) |

### Lookup helpers

```ts
frameById(id: string): Frame            // throws on unknown id
framesFor(animId: string): Frame[]      // animation → frames
rectFor(frameId: string)                // {x,y,w,h} with half-texel inset (anti-bleed)
autotileFrame(mask: number, item?): Frame
canonicalMask(mask: number, size: 16 | 47): number
glyphFrame(char: string, item?): Frame
textSprites(text, origin, item?, scale?): SpriteSpec[]
shaderUniforms(time): Record<string, number | number[]>
```

### Rendering hooks (react-native-skia)

```ts
useAtlasImage(): SkImage | undefined     // loads ATLAS_SOURCE
useAtlasSprites(specs, scale?): { image, sprites, transforms, sampling }
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

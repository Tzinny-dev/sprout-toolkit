# 10-minute starter: from `pip install` to sprites on screen

This tutorial takes you from zero to a running Expo app that renders
procedural sprites — no game-dev experience needed. Every asset is generated
locally from a JSON spec: same seed, same pixels, every time.

> **Prerequisites:** Python 3.10+, Node 18+, and an Android emulator/iOS
> simulator (or the Expo Go app). ~10 minutes.
> **Scope:** this tutorial uses `sprout` + `npx` only — no git clone needed.

## 1. Install the toolkit (2 min)

```bash
pip install sprout-toolkit   # the command is `sprout`
# note: bare `pip install sprout` is an unrelated package
sprout --help
```

## 2. Create an Expo app (3 min)

```bash
npx create-expo-app@latest StarterApp --template blank-typescript
cd StarterApp
npx expo install @shopify/react-native-skia react-native-reanimated
```

These exact versions are verified together (Expo SDK 57 + Skia 2.6.2):

| package | version |
|---|---|
| `expo` | `~57.0.24` |
| `@shopify/react-native-skia` | `2.6.2` |
| `react-native-reanimated` | `4.5.1` |

## 3. Write the spec + generate the atlas (2 min)

Save this as `starter.json` in the project root — 8 walk frames + 4 prop
frames. (It also ships as `specs/starter.json` in the GitHub repo.)

```json
{
  "name": "starter_atlas",
  "seed": 7,
  "target": "expo-rn-skia",
  "files": { "atlas": "atlas.png" },
  "layout": { "framePx": 64, "cols": 4, "tileLogical": 32, "sample": "nearest" },
  "items": [
    { "id": "hero", "generator": "blob_walk", "frames": 8 },
    { "id": "coin", "generator": "props", "frames": 4, "params": { "kind": "flower" } }
  ],
  "animations": { "walk": { "frames": "hero", "fps": 8, "loop": true } }
}
```

Then generate — no editor, one command:

```bash
# fastest: writes starter.json + generates in one step
sprout init --out ./assets/starter

# or manually, if you prefer to see the spec first:
sprout generate starter.json --out ./assets/starter
# → assets/starter/{atlas.png, manifest.json, index.ts}
```

What you get:

| file | role |
|---|---|
| `atlas.png` | the spritesheet (12 frames, 4×3 grid) |
| `manifest.json` | machine-readable map: frame → coords, `walk` anim, seed |
| `index.ts` | typed module: `framesFor('walk')`, `useAtlasSprites`, `frameById` |

Sanity-check the spec any time:

```bash
sprout info specs/starter.json       # human report
sprout validate specs/starter.json   # schema + plugins OK
```

<details>
<summary>The spec (<code>specs/starter.json</code>)</summary>

```json
{
  "name": "starter_atlas",
  "seed": 7,
  "target": "expo-rn-skia",
  "files": { "atlas": "atlas.png" },
  "layout": { "framePx": 64, "cols": 4, "tileLogical": 32, "sample": "nearest" },
  "items": [
    { "id": "hero", "generator": "blob_walk", "frames": 8 },
    { "id": "coin", "generator": "props", "frames": 4, "params": { "kind": "flower" } }
  ],
  "animations": { "walk": { "frames": "hero", "fps": 8, "loop": true } }
}
```

Change `seed` → regenerate → different-but-reproducible pixels.
</details>

> Packaging note: the wheel ships the generators but not the example specs —
> `specs/` lives in the GitHub repo. For this tutorial, copy-paste the JSON
> above; to explore all generators, `git clone` the repo or browse
> `specs/` online.

## 4. Render it (3 min)

Replace `App.tsx` with:

```tsx
import { Atlas, Canvas } from '@shopify/react-native-skia';
import { StatusBar } from 'expo-status-bar';
import { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { framesFor, manifest, useAtlasSprites } from './assets/starter';

function Hero() {
  const walk = useMemo(() => framesFor('walk'), []);
  const sprites = useAtlasSprites(
    useMemo(
      () => walk.map((f, i) => ({ id: f.id, x: 24 + i * 40, y: 300 })),
      [walk],
    ),
  );
  return (
    <Atlas
      image={sprites.image}
      sprites={sprites.sprites}
      transforms={sprites.transforms}
      sampling={sprites.sampling}
    />
  );
}

export default function App() {
  return (
    <View style={styles.container}>
      <Canvas style={StyleSheet.absoluteFill}>
        <Hero />
      </Canvas>
      <Text style={styles.hud}>
        {manifest.name} · seed {manifest.seed}
      </Text>
      <StatusBar style="auto" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1b3b52',
    alignItems: 'center',
    justifyContent: 'center',
  },
  hud: { color: '#fff', position: 'absolute', top: 64 },
});
```

How it works: `framesFor('walk')` resolves the 8 hero frames from the
manifest; `useAtlasSprites` turns `{ id, x, y }` specs into Skia rect/transform
buffers; `<Atlas>` draws them in one batch. `frameScale`
(`tileLogical / framePx = 0.5`) maps 64 px frames to 32 pt on screen.

## 5. Run it (1 min)

```bash
npx tsc --noEmit        # typecheck: clean
npx expo start          # scan the QR with Expo Go, or press `a` for Android
```

You should see 8 hero blobs in a row on a sea-blue background with
`starter_atlas · seed 7` on top.

> Verified end-to-end 2026-09-20: `tsc` clean + `expo export` bundles
> `assets/starter/atlas.png` (Metro picks up the generated `require()` —
> no extra config needed).

## Next steps

- Animate: drive the frame index with `useClock()` — see `BlobHero.tsx` in
  the demo app for the pattern (`clock.value / frameMs % frames.length`).
- Autotile island: `specs/autotile.json` + `autotileFrame(mask, 'terrain')` —
  see the Showcase section.
- Iterate: `sprout watch specs/ --out ./assets/starter` regenerates on save;
  Metro hot-reloads the PNG.
- Quality gates: `sprout lint` (atlas waste, empty frames),
  `sprout diff ./out/a ./out/b` (CRC + manifest compare for CI).

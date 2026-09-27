"""Exporters: build the spritesheet, the `manifest.json` (v0) and the
TypeScript `index.ts` module for Expo + react-native-skia.

The generated `index.ts` is the "wired" piece: it requires static assets
(mandatory for Metro/EAS Update), manifest types and frame helpers.
"""
from __future__ import annotations

import io
import json
import zlib
from pathlib import Path

from PIL import Image, ImageFont

from . import __version__, autotile, sksl
from .generators.base import FrameData
from .generators import get_generator
from .generators.font import resolve_font_path
from .spec import Spec


def shader_filename(spec: Spec) -> str:
    return f"{spec.name}.sksl"


def build_shader(spec: Spec) -> tuple[str, dict] | tuple[None, None]:
    """SkSL source + manifest `shader` block (or `(None, None)` if `runtime` is off)."""
    if spec.runtime is None:
        return None, None
    source = sksl.render_shader()
    uniforms = sksl.build_uniforms(spec.seed, spec.runtime, spec.layout.frame_px)
    block = {"file": shader_filename(spec), "uniforms": uniforms}
    return source, block


def build_tier_shaders(spec: Spec) -> dict[str, dict]:
    """name -> {source, file, template, uniforms} for each spec `tiers` entry."""
    out: dict[str, dict] = {}
    for name, rule in (spec.tiers or {}).items():
        template = rule["template"]
        out[name] = {
            "source": sksl.render_tier_shader(template),
            "file": sksl.tier_shader_filename(spec.name, name),
            "template": template,
            "uniforms": sksl.tier_shader(spec.seed, template, rule["params"]),
        }
    return out


def _frame_ids(item_id: str, count: int) -> list[str]:
    return [f"{item_id}_{i:02d}" for i in range(count)]


def render_items(spec: Spec) -> list[list[FrameData]]:
    """Generates frames for all items, in spec order."""
    out: list[list[FrameData]] = []
    offset = 0
    for item in spec.items:
        gen = get_generator(item.generator)()
        frames = gen.generate(spec.seed, item.frames, spec.layout.frame_px,
                              item.params, base=offset)
        for fid, fr in zip(_frame_ids(item.id, item.frames), frames, strict=True):
            fr.id = fid
        out.append(frames)
        offset += item.frames
    return out


def build_sheet(spec: Spec, items_frames: list[list[FrameData]]) -> tuple[Image.Image, list[dict]]:
    """Packs frames into a row-major grid -> (RGBA sheet, records with coords)."""
    cols = spec.layout.cols
    frame = spec.layout.frame_px
    rows = spec.layout.resolve_rows(spec.total_frames)
    sheet = Image.new("RGBA", (cols * frame, rows * frame), (0, 0, 0, 0))
    records: list[dict] = []
    i = 0
    for frames in items_frames:
        for fr in frames:
            col, row = i % cols, i // cols
            x, y = col * frame, row * frame
            sheet.paste(fr.image, (x, y), fr.image if fr.image.mode == "RGBA" else None)
            record = {
                "id": fr.id, "col": col, "row": row,
                "x": x, "y": y, "w": frame, "h": frame,
            }
            if "anchor" in fr.meta:
                record["anchor"] = fr.meta["anchor"]
            records.append(record)
            i += 1
    return sheet, records


def build_autotile_map(spec: Spec, items_frames: list[list[FrameData]]) -> dict:
    """Manifest `autotile` block: item -> {size, mask: {mask: frameId}}."""
    items: dict[str, dict] = {}
    for item, frames in zip(spec.items, items_frames, strict=True):
        if item.autotile is None:
            continue
        items[item.id] = {
            "size": item.autotile,
            "mask": {str(fr.meta["autotile_mask"]): fr.id for fr in frames},
        }
    return {"bitmask": autotile.BITMASK, "items": items} if items else {}


def build_font_map(spec: Spec, items_frames: list[list[FrameData]]) -> dict:
    """Manifest `font` block: item -> {ascent, descent, glyphs}."""
    items: dict[str, dict] = {}
    for item, frames in zip(spec.items, items_frames, strict=True):
        if item.generator != "font":
            continue
        font_path = resolve_font_path(item.params)
        size = int(item.params.get("size", spec.layout.frame_px * 0.6))
        face = ImageFont.truetype(font_path, size)
        ascent, descent = face.getmetrics()
        items[item.id] = {
            "ascent": ascent,
            "descent": descent,
            "glyphs": {
                fr.meta["char"]: {"id": fr.id, "advance": fr.meta["advance"]}
                for fr in frames
            },
        }
    return {"items": items} if items else {}


def build_manifest(spec: Spec, records: list[dict], atlas_name: str,
                   sheet: Image.Image, spec_path: str, autotile_map: dict | None = None,
                   shader_block: dict | None = None, font_map: dict | None = None,
                   mipmaps_block: dict | None = None,
                   silhouette_name: str | None = None,
                   tiers_block: dict | None = None) -> dict:
    anim: dict[str, dict] = {}
    for name, a in spec.animations.items():
        item = next(it for it in spec.items if it.id == a.frames)
        anim[name] = {
            "frames": _frame_ids(a.frames, item.frames),
            "fps": a.fps,
            "loop": a.loop,
        }
    tile_ids: list[str] = []
    for item in spec.items:
        if item.generator == "terrain":
            tile_ids += _frame_ids(item.id, item.frames)
    tint_items = {it.id: it.tint for it in spec.items if it.tint != "none"}
    tint_block: dict | None = None
    if spec.colors or tint_items:
        tint_block = {
            "colors": [{"key": c.key, "hex": c.hex} for c in spec.colors],
            "items": tint_items,
        }
    return {
        "schema": "sprout/manifest@0",
        "name": spec.name,
        "seed": spec.seed,
        "kind": "atlas",
        "files": {
            "atlas": atlas_name,
            "atlasW": sheet.width,
            "atlasH": sheet.height,
            **({"silhouette": silhouette_name} if silhouette_name else {}),
        },
        "units": {
            "tileLogical": spec.layout.tile_logical,
            "framePx": spec.layout.frame_px,
            "sample": spec.layout.sample,
        },
        "frames": records,
        "anim": anim,
        "tiles": {"ids": tile_ids},
        "meta": {
            "provenance": {"spec": spec_path, "git": ""},
            "generator": {"name": "sprout", "version": __version__},
        },
        **({"autotile": autotile_map} if autotile_map else {}),
        **({"shader": shader_block} if shader_block else {}),
        **({"tiers": tiers_block} if tiers_block else {}),
        **({"font": font_map} if font_map else {}),
        **({"mipmaps": mipmaps_block} if mipmaps_block else {}),
        **({"tint": tint_block} if tint_block else {}),
    }


def apply_png_mode(img: Image.Image, png_mode: str) -> Image.Image:
    """Converts the atlas to the chosen export mode before saving.

    "png24" drops the alpha channel (only suitable for atlases without real
    transparency, e.g. `terrain`). "png8" quantizes to a 256-color indexed
    palette — PIL preserves the exact alpha per palette entry, so
    transparency survives (verified with opaque, semi-transparent and empty
    pixels)."""
    if png_mode == "png24":
        return img.convert("RGB")
    if png_mode == "png8":
        return img.quantize(colors=256)
    return img  # "rgba" (default): no change


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes atomically (temp file + os.replace).

    Readers never observe a half-written file: the target path appears only
    when the content is complete. Matters for `sprout watch` consumers (and
    tests) that poll for the file's existence while a generation is in flight.
    """
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_png(sheet: Image.Image, path: Path, png_mode: str = "rgba") -> int:
    buf = io.BytesIO()
    apply_png_mode(sheet, png_mode).save(buf, format="PNG")
    data = buf.getvalue()
    _atomic_write_bytes(path, data)
    return zlib.crc32(data) & 0xFFFFFFFF


def blacken(sheet: Image.Image) -> Image.Image:
    """Black × original alpha — the SILHOUETTE_MATRIX, prebaked."""
    rgb = Image.new("L", sheet.size, 0)
    out = Image.merge("RGBA", (rgb, rgb, rgb, sheet.getchannel("A")))
    return out


_TP_FORMAT = {"rgba": "RGBA8888", "png24": "RGB888", "png8": "I8"}


def texturepacker_filename(spec: Spec) -> str:
    return f"{spec.name}.tpsheet.json"


def build_texturepacker(spec: Spec, records: list[dict], atlas_name: str,
                        sheet: Image.Image, png_mode: str) -> dict:
    """TexturePacker "JSON (Hash)" format — compatible with Phaser/PixiJS/
    etc. Does not replace `manifest.json`, it's emitted alongside it (opt-in)."""
    frames = {
        f"{r['id']}.png": {
            "frame": {"x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"]},
            "rotated": False,
            "trimmed": False,
            "spriteSourceSize": {"x": 0, "y": 0, "w": r["w"], "h": r["h"]},
            "sourceSize": {"w": r["w"], "h": r["h"]},
        }
        for r in records
    }
    return {
        "frames": frames,
        "meta": {
            "app": "sprout",
            "version": __version__,
            "image": atlas_name,
            "format": _TP_FORMAT[png_mode],
            "size": {"w": sheet.width, "h": sheet.height},
            "scale": "1",
        },
    }


def write_texturepacker(tp: dict, path: Path) -> None:
    _atomic_write_bytes(path, (json.dumps(tp, indent=2) + "\n").encode())


def compute_mipmap_meta(sheet: Image.Image, spec: Spec, levels: int) -> list[dict]:
    """Pure metadata for the mip levels (scale/file/w/h), without touching disk:
    needed before the `skip_existing` check and for the manifest's `mipmaps`
    block. Stops if a dimension would drop below 4px."""
    base = Path(spec.filename)
    out: list[dict] = []
    scale = 1.0
    for _ in range(levels):
        scale /= 2
        w, h = round(sheet.width * scale), round(sheet.height * scale)
        if w < 4 or h < 4:
            break
        out.append({
            "scale": scale,
            "file": f"{base.stem}@{scale:g}x{base.suffix}",
            "w": w, "h": h,
        })
    return out


def write_mipmap_files(sheet: Image.Image, out_dir: Path, png_mode: str,
                       meta: list[dict]) -> None:
    """Writes each mip level: `Image.BOX` (area-average filter, correct for
    mip generation — avoids Lanczos ringing)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for lvl in meta:
        img = sheet.resize((lvl["w"], lvl["h"]), Image.BOX)
        buf = io.BytesIO()
        apply_png_mode(img, png_mode).save(buf, format="PNG")
        _atomic_write_bytes(out_dir / lvl["file"], buf.getvalue())


def write_manifest(manifest: dict, path: Path) -> None:
    _atomic_write_bytes(path, (json.dumps(manifest, indent=2) + "\n").encode())


def emit_index_ts(manifest: dict, out_path: Path) -> None:
    _atomic_write_bytes(out_path, _ts_source(manifest).encode())


def emit_tier_index_ts(out_dir: Path, tiers: list[tuple[int, dict]]) -> None:
    """Combined index.ts for resolution tiers: `atlasSources` + `pickTier`.

    `tiers` is (px, manifest) per generated tier; each tier lives in
    `<out_dir>/<px>/` with its own atlas + manifest + index.ts.
    """
    tiers = sorted(tiers, key=lambda t: t[0])
    if not tiers:
        raise ValueError("emit_tier_index_ts: no tiers")
    base_px, _ = tiers[0]
    px_list = ", ".join(str(px) for px, _ in tiers)
    entries = "\n".join(
        f"  {px}: {{ atlas: require('./{px}/{m['files']['atlas']}') as number,"
        f" manifest: require('./{px}/manifest.json') as Manifest }},"
        for px, m in tiers
    )
    source = f"""// GENERATED by {__version__} — DO NOT EDIT. (resolution tiers)
import type {{ Manifest }} from './{base_px}/index';
export * from './{base_px}/index';

export type Tier = {' | '.join(str(px) for px, _ in tiers)};
export const TIERS: readonly Tier[] = [{px_list}];

export const atlasSources: Record<Tier, {{ atlas: number; manifest: Manifest }}> = {{
{entries}
}};

/** Smallest tier >= px; the largest tier when px exceeds them all. */
export function pickTier(px: number): Tier {{
  for (const t of TIERS) {{
    if (t >= px) return t;
  }}
  return TIERS[TIERS.length - 1];
}}
"""
    _atomic_write_bytes(out_dir / "index.ts", source.encode())


def _ts_tier_block(m: dict) -> str:
    """TIER_SHADERS + tierUniforms (uniforms read from manifest.tiers)."""
    tiers = m.get("tiers") or {}
    entries: list[str] = []
    for name, t in tiers.items():
        source = sksl.render_tier_shader(t["template"])
        escaped = (
            source.replace("\\", "\\\\").replace("`", "\\`")
            .replace("${", "\\${")
        )
        entries.append(f"  {name}: `{escaped}`")
    if not tiers:
        body = ""
        shape = "export const TIER_SHADERS: Record<string, string> = {} as const;\n"
    else:
        body = ",\n".join(entries)
        shape = ("export const TIER_SHADERS: Record<string, string> = {\n"
                 f"{body}\n"
                 "} as const;\n")
    return (
        f"{shape}"
        "export type TierName = string;\n"
        "\n"
        "/** Uniforms for a tier effect (seed-derived; `time` is the anim clock). */\n"
        "export function tierUniforms(name: TierName, time = 0): Record<string, number> {\n"
        "  const u = manifest.tiers?.[name]?.uniforms;\n"
        "  if (!u) throw new Error('unknown tier shader: ' + name);\n"
        "  return { ...u, time };\n"
        "}\n"
    )


def _ts_shader_block(m: dict) -> str:
    shader = m.get("shader")
    if not shader:
        return (
            "export const SHADER_SKS: string | null = null;\n"
            "export const SHADER_DEFAULTS = null;\n\n"
            "export function shaderUniforms(_time = 0): null {\n"
            "  return null;\n"
            "}\n"
        )
    source = sksl.render_shader()
    escaped = (
        source.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    )
    uniforms_json = json.dumps(shader["uniforms"], indent=2)
    return f"""export const SHADER_SKS: string = `{escaped}`;
export const SHADER_DEFAULTS = {uniforms_json} as const;

export function shaderUniforms(time = 0): Record<string, number | number[]> {{
  const u = manifest.shader?.uniforms;
  if (!u) throw new Error('manifest has no shader block (spec.runtime)');
  return {{
    u_freq: u.freq,
    u_oct: u.octaves,
    u_seed: u.seed,
    u_tile: [u.tileWidth, u.tileHeight],
    u_time: time,
    u_base: [...u.base],
    u_accent: [...u.accent],
  }};
}}
"""


def _ts_tint_block() -> str:
    """Runtime tint helpers (color variants) — see docs/api.md.

    Emitted unconditionally so the API surface is identical across atlases:
    with a `tint` manifest block the maps are populated; without it they are
    empty and `tintColor` throws on lookup.
    """
    return """
// --- Runtime tint (color variants) ---
export type TintMode = 'shade' | 'full';

export interface TintColor { key: string; hex: string }
export interface TintBlock { colors: TintColor[]; items: Record<string, TintMode> }

export const TINTS: Record<string, string> = Object.fromEntries(
  (manifest.tint?.colors ?? []).map((c) => [c.key, c.hex]),
);
export const TINT_MODES: Record<string, TintMode> = manifest.tint?.items ?? {};

/** Declared tint mode for an item ('none' when the item bakes its colors). */
export function tintModeFor(itemId: string): TintMode | 'none' {
  return TINT_MODES[itemId] ?? 'none';
}

/** '#RGB' | '#RRGGBB' -> [r, g, b] in 0..1 */
export function hexToRgb(hex: string): [number, number, number] {
  let h = hex.replace('#', '').trim();
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  if (h.length !== 6 || /[^0-9a-fA-F]/.test(h)) {
    throw new Error(`Invalid hex color: ${hex}`);
  }
  return [
    parseInt(h.slice(0, 2), 16) / 255,
    parseInt(h.slice(2, 4), 16) / 255,
    parseInt(h.slice(4, 6), 16) / 255,
  ];
}

/**
 * 4x5 row-major Skia color matrix for a tint:
 * - 'shade': keeps the sprite's Rec.709 luminance and re-hues it
 *   (correct on colored art; black outlines stay black).
 * - 'full' : pure per-channel multiply — identical to 'shade' on
 *   neutral/tint-ready art (gray ramp).
 */
export function colorMatrixFor(hex: string, mode: TintMode = 'shade'): number[] {
  const [r, g, b] = hexToRgb(hex);
  if (mode === 'full') {
    return [r, 0, 0, 0, 0, 0, g, 0, 0, 0, 0, 0, b, 0, 0, 0, 0, 0, 1, 0];
  }
  const k = [0.2126, 0.7152, 0.0722]; // Rec.709 luminance weights
  return [
    k[0] * r, k[1] * r, k[2] * r, 0, 0,
    k[0] * g, k[1] * g, k[2] * g, 0, 0,
    k[0] * b, k[1] * b, k[2] * b, 0, 0,
    0, 0, 0, 1, 0,
  ];
}

/** Black x original alpha: the "hidden item" silhouette (mode ciego). */
export const SILHOUETTE_MATRIX: number[] = [
  0, 0, 0, 0, 0,
  0, 0, 0, 0, 0,
  0, 0, 0, 0, 0,
  0, 0, 0, 1, 0,
];

/** SkPaint carrying the tint color filter: <Atlas paint={tintPaint(hex)} />. */
export function tintPaint(hex: string, mode: TintMode = 'shade'): SkPaint {
  const paint = Skia.Paint();
  paint.setColorFilter(Skia.ColorFilter.MakeMatrix(colorMatrixFor(hex, mode)));
  return paint;
}

/** SkPaint that flattens every sprite to a black silhouette. */
export function silhouettePaint(): SkPaint {
  const paint = Skia.Paint();
  paint.setColorFilter(Skia.ColorFilter.MakeMatrix(SILHOUETTE_MATRIX));
  return paint;
}

/** SkColor for one declared tint key (throws when unknown). */
export function tintColor(colorKey: string): SkColor {
  const hex = TINTS[colorKey];
  if (!hex) throw new Error(`Unknown tint color: ${colorKey}`);
  return Skia.Color(hex);
}

/**
 * Per-sprite colors for
 * `<Atlas colors={tintColors(specs, key)} colorBlendMode="modulate" />`.
 * Modulate = texture x color ('full'); on tint-ready (neutral) art that is
 * indistinguishable from 'shade'. One color per batch -> computed once.
 */
export function tintColors(specs: readonly { id: string }[], colorKey: string): SkColor[] {
  const color = tintColor(colorKey);
  return specs.map(() => color);
}

/** Per-sprite colors that turn every sprite into a black silhouette. */
export function silhouetteColors(specs: readonly { id: string }[]): SkColor[] {
  const black = Skia.Color('#000000');
  return specs.map(() => black);
}
"""


def _ts_source(m: dict) -> str:
    atlas = m["files"]["atlas"]
    shader_block = _ts_shader_block(m)
    tier_block = _ts_tier_block(m)
    tint_block = _ts_tint_block()
    sil_name = m["files"].get("silhouette")
    sil_source = (
        f"export const SILHOUETTE_SOURCE = require('./{sil_name}') as number;\n"
        if sil_name else
        "export const SILHOUETTE_SOURCE: number | null = null;\n"
    )
    return f"""// GENERATED by sprout {__version__} — DO NOT EDIT.
import {{
  FilterMode,
  Skia,
  useImage,
  useRectBuffer,
  useRSXformBuffer,
}} from '@shopify/react-native-skia';
import type {{
  SkColor,
  SkHostRect,
  SkImage,
  SkPaint,
  SkPicture,
  SkRSXform,
}} from '@shopify/react-native-skia';
import {{ useMemo }} from 'react';

export interface Frame {{
  id: string;
  col: number;
  row: number;
  x: number;
  y: number;
  w: number;
  h: number;
  anchor?: {{ x: number; y: number }};
}}

export interface Anim {{
  frames: string[];
  fps: number;
  loop: boolean;
}}

export const AUTOTILE_BITS = {{
  N: 1, NE: 2, E: 4, SE: 8, S: 16, SW: 32, W: 64, NW: 128,
}} as const;

export interface AutotileItem {{
  size: 16 | 47;
  mask: Record<string, string>;
}}

export interface Autotile {{
  bitmask: string;
  items: Record<string, AutotileItem>;
}}

export interface ShaderUniforms {{
  freq: number;
  octaves: number;
  seed: number;
  tileable: boolean;
  tileWidth: number;
  tileHeight: number;
  period: number;
  time: number;
  base: number[];
  accent: number[];
}}

export interface ShaderBlock {{
  file: string;
  uniforms: ShaderUniforms;
}}

export interface TierBlock {{
  file: string;
  template: string;
  uniforms: Record<string, number>;
}}

export interface GlyphEntry {{
  id: string;
  advance: number;
}}

export interface FontItem {{
  ascent: number;
  descent: number;
  glyphs: Record<string, GlyphEntry>;
}}

export interface FontBlock {{
  items: Record<string, FontItem>;
}}

export interface MipmapLevel {{
  scale: number;
  file: string;
  w: number;
  h: number;
}}

export interface MipmapsBlock {{
  levels: MipmapLevel[];
}}

export interface GeneratorMeta {{
  name: string;
  version: string;
}}
export interface ManifestMeta {{
  provenance: {{ spec: string; git: string }};
  generator: GeneratorMeta;
}}

export interface Manifest {{
  schema: string;
  name: string;
  seed: number;
  kind: string;
  files: {{ atlas: string; atlasW: number; atlasH: number; silhouette?: string }};
  units: {{ tileLogical: number; framePx: number; sample: 'nearest' | 'linear' }};
  frames: Frame[];
  anim: Record<string, Anim>;
  tiles: {{ ids: string[] }};
  autotile?: Autotile;
  shader?: ShaderBlock;
  tiers?: Record<string, TierBlock>;
  font?: FontBlock;
  mipmaps?: MipmapsBlock;
  tint?: TintBlock;
  meta: ManifestMeta;
}}

{shader_block}
{tier_block}
export const ATLAS_SOURCE = require('./{atlas}') as number;
{sil_source}export const manifest: Manifest = require('./manifest.json') as Manifest;
export const GENERATOR = manifest.meta?.generator ?? {{ name: 'sprout', version: 'unknown' }};
export const sampleMode =
  manifest.units.sample === 'nearest' ? FilterMode.Nearest : FilterMode.Linear;

const byId = new Map(manifest.frames.map((f) => [f.id, f]));

export function frameById(id: string): Frame {{
  const frame = byId.get(id);
  if (!frame) throw new Error(`Unknown frame: ${{id}}`);
  return frame;
}}

export function framesFor(animId: string): Frame[] {{
  const anim = manifest.anim[animId];
  if (!anim) throw new Error(`Unknown animation: ${{animId}}`);
  return anim.frames.map(frameById);
}}

export const tileFrames: Frame[] = manifest.tiles.ids.map(frameById);

export const frameScale = manifest.units.tileLogical / manifest.units.framePx;
export const atlasSampling = {{ filter: sampleMode }};

{tint_block}
export function rectFor(frameId: string): {{ x: number; y: number; w: number; h: number }} {{
  const f = frameById(frameId);
  // Half-texel inset: avoids bleeding from the atlas' neighboring frame when
  // nearest sampling falls outside the rect (clamp-to-edge) due to rounding
  // in the destination scale (e.g. a 64px frame to an 84px device pixel with DPR 2.625).
  const e = 0.5;
  return {{ x: f.x + e, y: f.y + e, w: f.w - 2 * e, h: f.h - 2 * e }};
}}

export function useAtlasImage() {{
  return useImage(ATLAS_SOURCE);
}}

/** Loads SILHOUETTE_SOURCE (prebaked mask; `null` without --silhouette). */
export function useSilhouetteImage(): SkImage | null {{
  return SILHOUETTE_SOURCE === null ? null : useImage(SILHOUETTE_SOURCE);
}}

export interface SpriteSpec {{
  id: string;
  x: number;
  y: number;
  scale?: number;
}}

export function useAtlasSprites(specs: readonly SpriteSpec[], scale = frameScale) {{
  const image = useAtlasImage();
  const rects = specs.map((s) => rectFor(s.id));
  const frames = specs.map((s) => frameById(s.id));
  // Compensates for rectFor's inset: adjusts the scale so the destination size
  // (scale * framePx) doesn't change even though the trimmed source is 2e px smaller.
  const scales = specs.map(
    (s, i) => (s.scale ?? scale) * (frames[i].w / rects[i].w),
  );
  const sprites = useRectBuffer(specs.length, (rect, i) => {{
    'worklet';
    const f = rects[i];
    rect.setXYWH(f.x, f.y, f.w, f.h);
  }});
  const transforms = useRSXformBuffer(specs.length, (xform, i) => {{
    'worklet';
    const s = specs[i];
    xform.set(scales[i], 0, s.x, s.y);
  }});
  return {{ image, sprites, transforms, sampling: atlasSampling }};
}}

/**
 * Centers a frame's box inside a `size` x `size` target at (cx, cy) —
 * the placement helper for badges, circles, and cards.
 */
export function spriteLayout(id: string, cx: number, cy: number, size: number): SpriteSpec {{
  const f = frameById(id);
  const box = Math.max(f.w, f.h);
  return {{ id, x: cx, y: cy, scale: size / box }};
}}

/**
 * `useAtlasSprites` + per-sprite black x alpha: the runtime silhouette
 * path (zero bundle cost — no extra atlas frames).
 *
 *   const s = useSilhouetteSprites(specs);
 *   <Atlas {{...s}} colors={{s.colors}} colorBlendMode="modulate" />
 */
export function useSilhouetteSprites(specs: readonly SpriteSpec[], scale = frameScale) {{
  const base = useAtlasSprites(specs, scale);
  return {{ ...base, colors: silhouetteColors(specs) }};
}}

export function useAtlasGrid(
  ids: readonly string[],
  cols: number,
  origin: {{ x: number; y: number }} = {{ x: 0, y: 0 }},
  tile: number = manifest.units.tileLogical,
) {{
  const specs: SpriteSpec[] = ids.map((id, i) => ({{
    id,
    x: origin.x + (i % cols) * tile,
    y: origin.y + Math.floor(i / cols) * tile,
    scale: tile / manifest.units.framePx,
  }}));
  return useAtlasSprites(specs);
}}

// --- Imperative batch mode (post-MVP, §11) ---
// Records N sprites into a SkPicture with a single canvas.drawAtlas: one draw
// call per texture, without the per-transform JSI crossing of the declarative
// path (<Atlas> + reanimated buffers) that hurts low-end Android (#2521/#2688).
// The pools are mutated in-place: recording doesn't allocate in steady state.

/** Typed read-only specs (flat tuples, ready to record). */
export type SpriteSpecData = readonly (readonly [
  id: string,
  x: number,
  y: number,
  scale: number,
])[];

/** Converts SpriteSpec[] to flat tuples. */
export function toSpecData(
  specs: readonly SpriteSpec[],
  scale = frameScale,
): SpriteSpecData {{
  return specs.map((s) => [s.id, s.x, s.y, s.scale ?? scale]);
}}

/** Inflates flat specs into mutable rects/xforms pools ready to record. */
export function inflateSpecData(data: SpriteSpecData): {{
  rects: SkHostRect[];
  xforms: SkRSXform[];
}} {{
  const rects: SkHostRect[] = new Array(data.length);
  const xforms: SkRSXform[] = new Array(data.length);
  for (let i = 0; i < data.length; i++) {{
    const [id, x, y, scale] = data[i];
    const f = frameById(id);
    // Same half-texel inset and scale compensation as rectFor:
    // the destination stays scale * framePx despite the trimmed source.
    const e = 0.5;
    rects[i] = Skia.XYWHRect(f.x + e, f.y + e, f.w - 2 * e, f.h - 2 * e);
    xforms[i] = Skia.RSXform(scale * (f.w / (f.w - 2 * e)), 0, x, y);
  }}
  return {{ rects, xforms }};
}}

/**
 * Records static specs into a SkPicture with a single drawAtlas.
 * Optional `dpr`: if passed, aligns each sprite to a device pixel
 * (recommended with non-integer DPR and nearest sampling, see IslandMap).
 */
export function makeStaticAtlasPicture(
  data: SpriteSpecData,
  image: SkImage,
  dpr?: number,
): SkPicture {{
  let rects: SkHostRect[];
  let xforms: SkRSXform[];
  if (dpr !== undefined) {{
    const snapped: [string, number, number, number][] = data.map(
      ([id, x, y, scale]) => [
        id,
        Math.round(x * dpr) / dpr,
        Math.round(y * dpr) / dpr,
        scale,
      ],
    );
    const inflated = inflateSpecData(snapped);
    rects = inflated.rects;
    xforms = inflated.xforms;
  }} else {{
    const inflated = inflateSpecData(data);
    rects = inflated.rects;
    xforms = inflated.xforms;
  }}
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const framePx = manifest.units.framePx;
  for (let i = 0; i < xforms.length; i++) {{
    const s = xforms[i].scos;
    const half = (framePx * s) / 2;
    minX = Math.min(minX, xforms[i].tx - half);
    minY = Math.min(minY, xforms[i].ty - half);
    maxX = Math.max(maxX, xforms[i].tx + half);
    maxY = Math.max(maxY, xforms[i].ty + half);
  }}
  const recorder = Skia.PictureRecorder();
  const canvas = recorder.beginRecording(
    Skia.XYWHRect(minX, minY, maxX - minX, maxY - minY),
  );
  canvas.drawAtlas(
    image,
    rects,
    xforms,
    Skia.Paint(),
    undefined,
    undefined,
    atlasSampling,
  );
  return recorder.finishRecordingAsPicture();
}}

/**
 * Preallocated buffers + shared imperative paint for animated batches.
 * `count` sets the capacity (reserved once, no realloc per frame);
 * `specs.length` active sprites are written with `inflateInto` each frame.
 */
export function useAtlasBatch(
  specs: readonly SpriteSpec[],
  extra = 0,
  scale = frameScale,
) {{
  const data = useMemo(
    () => toSpecData(specs, scale),
    [specs, scale],
  );
  const rects = useRectBuffer(specs.length + extra, (rect) => {{
    'worklet';
    rect.setXYWH(0, 0, 0, 0);
  }});
  const xforms = useRSXformBuffer(specs.length + extra, (xform) => {{
    'worklet';
    xform.set(1, 0, 0, 0);
  }});
  const paint = useMemo(() => Skia.Paint(), []);
  return {{
    data,
    capacity: specs.length + extra,
    rects,
    xforms,
    paint,
    /** Flushes the first specs.length positions of the buffers. */
    inflateInto: () => {{
      const arr = rects.value as SkHostRect[];
      const xf = xforms.value as SkRSXform[];
      for (let i = 0; i < data.length; i++) {{
        const [id, x, y, s] = data[i];
        const f = frameById(id);
        const e = 0.5;
        arr[i].setXYWH(f.x + e, f.y + e, f.w - 2 * e, f.h - 2 * e);
        xf[i].set(s * (f.w / (f.w - 2 * e)), 0, x, y);
      }}
    }},
  }};
}}

const SIDES =
  AUTOTILE_BITS.N | AUTOTILE_BITS.E | AUTOTILE_BITS.S | AUTOTILE_BITS.W;

export function canonicalMask(mask: number, size: 16 | 47): number {{
  if (size === 16) return mask & SIDES;
  let m = mask & SIDES;
  if (mask & AUTOTILE_BITS.NE && mask & AUTOTILE_BITS.N && mask & AUTOTILE_BITS.E)
    m |= AUTOTILE_BITS.NE;
  if (mask & AUTOTILE_BITS.SE && mask & AUTOTILE_BITS.S && mask & AUTOTILE_BITS.E)
    m |= AUTOTILE_BITS.SE;
  if (mask & AUTOTILE_BITS.SW && mask & AUTOTILE_BITS.S && mask & AUTOTILE_BITS.W)
    m |= AUTOTILE_BITS.SW;
  if (mask & AUTOTILE_BITS.NW && mask & AUTOTILE_BITS.N && mask & AUTOTILE_BITS.W)
    m |= AUTOTILE_BITS.NW;
  return m;
}}

export function autotileFrame(mask: number, item = 'tiles'): Frame {{
  const auto = manifest.autotile;
  if (!auto) throw new Error('manifest has no autotile block');
  const entry = auto.items[item];
  if (!entry) throw new Error(`Unknown autotile: ${{item}}`);
  const m = canonicalMask(mask, entry.size);
  const id = entry.mask[String(m)];
  if (!id) throw new Error(`autotile has no frame for mask ${{m}} in ${{item}}`);
  return frameById(id);
}}

export function glyphFrame(char: string, item = 'font'): Frame {{
  const fontBlock = manifest.font;
  if (!fontBlock) throw new Error('manifest has no font block');
  const entry = fontBlock.items[item];
  if (!entry) throw new Error(`Unknown font: ${{item}}`);
  const glyph = entry.glyphs[char];
  if (!glyph) throw new Error(`glyph has no frame for character '${{char}}' in ${{item}}`);
  return frameById(glyph.id);
}}

/** Builds SpriteSpec[] for a text, advancing in x by each glyph's width. */
export function textSprites(
  text: string,
  origin: {{ x: number; y: number }},
  item = 'font',
  scale = frameScale,
): SpriteSpec[] {{
  const fontBlock = manifest.font;
  if (!fontBlock) throw new Error('manifest has no font block');
  const entry = fontBlock.items[item];
  if (!entry) throw new Error(`Unknown font: ${{item}}`);
  const specs: SpriteSpec[] = [];
  let x = origin.x;
  for (const ch of text) {{
    const glyph = entry.glyphs[ch];
    if (!glyph) continue;
    specs.push({{ id: glyph.id, x, y: origin.y, scale }});
    x += glyph.advance * scale;
  }}
  return specs;
}}
"""
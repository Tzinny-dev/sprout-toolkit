"""Exporters: construyen el spritesheet, el `manifest.json` (v0) y el módulo
TypeScript `index.ts` para Expo + react-native-skia.

El `index.ts` generado es la pieza "cableada": requiere estáticos (obligatorios
para Metro/EAS Update), tipos del manifest y helpers de frames.
"""
from __future__ import annotations

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
    """Fuente SkSL + bloque `shader` del manifest (o `(None, None)` si `runtime` off)."""
    if spec.runtime is None:
        return None, None
    source = sksl.render_shader()
    uniforms = sksl.build_uniforms(spec.seed, spec.runtime, spec.layout.frame_px)
    block = {"file": shader_filename(spec), "uniforms": uniforms}
    return source, block


def _frame_ids(item_id: str, count: int) -> list[str]:
    return [f"{item_id}_{i:02d}" for i in range(count)]


def render_items(spec: Spec) -> list[list[FrameData]]:
    """Genera los frames de todos los items, en orden de la spec."""
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
    """Empaqueta frames en grilla row-major -> (sheet RGBA, records con coords)."""
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
            records.append({
                "id": fr.id, "col": col, "row": row,
                "x": x, "y": y, "w": frame, "h": frame,
            })
            i += 1
    return sheet, records


def build_autotile_map(spec: Spec, items_frames: list[list[FrameData]]) -> dict:
    """Bloque `autotile` del manifest: item -> {size, mask: {máscara: frameId}}."""
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
    """Bloque `font` del manifest: item -> {ascent, descent, glyphs}."""
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
                   shader_block: dict | None = None, font_map: dict | None = None) -> dict:
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
    return {
        "schema": "sprout/manifest@0",
        "name": spec.name,
        "seed": spec.seed,
        "kind": "atlas",
        "files": {
            "atlas": atlas_name,
            "atlasW": sheet.width,
            "atlasH": sheet.height,
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
        **({"font": font_map} if font_map else {}),
    }


def write_png(sheet: Image.Image, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    return zlib.crc32(path.read_bytes()) & 0xFFFFFFFF


def write_manifest(manifest: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def emit_index_ts(manifest: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_ts_source(manifest))


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
  if (!u) throw new Error('manifest sin bloque shader (spec.runtime)');
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


def _ts_source(m: dict) -> str:
    atlas = m["files"]["atlas"]
    shader_block = _ts_shader_block(m)
    return f"""// GENERATED by sprout {__version__} — DO NOT EDIT.
import {{
  FilterMode,
  Skia,
  useImage,
  useRectBuffer,
  useRSXformBuffer,
}} from '@shopify/react-native-skia';
import type {{
  SkHostRect,
  SkImage,
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

export interface Manifest {{
  schema: string;
  name: string;
  seed: number;
  kind: string;
  files: {{ atlas: string; atlasW: number; atlasH: number }};
  units: {{ tileLogical: number; framePx: number; sample: 'nearest' | 'linear' }};
  frames: Frame[];
  anim: Record<string, Anim>;
  tiles: {{ ids: string[] }};
  autotile?: Autotile;
  shader?: ShaderBlock;
  font?: FontBlock;
  meta: unknown;
}}

{shader_block}
export const ATLAS_SOURCE = require('./{atlas}') as number;
export const manifest: Manifest = require('./manifest.json') as Manifest;
export const sampleMode =
  manifest.units.sample === 'nearest' ? FilterMode.Nearest : FilterMode.Linear;

const byId = new Map(manifest.frames.map((f) => [f.id, f]));

export function frameById(id: string): Frame {{
  const frame = byId.get(id);
  if (!frame) throw new Error(`Frame desconocido: ${{id}}`);
  return frame;
}}

export function framesFor(animId: string): Frame[] {{
  const anim = manifest.anim[animId];
  if (!anim) throw new Error(`Animación desconocida: ${{animId}}`);
  return anim.frames.map(frameById);
}}

export const tileFrames: Frame[] = manifest.tiles.ids.map(frameById);

export const frameScale = manifest.units.tileLogical / manifest.units.framePx;
export const atlasSampling = {{ filter: sampleMode }};

export function rectFor(frameId: string): {{ x: number; y: number; w: number; h: number }} {{
  const f = frameById(frameId);
  // Inset de medio texel: evita sangrado del frame vecino del atlas cuando el
  // muestreo nearest cae fuera del rect (clamp-to-edge) por redondeo del
  // escalado destino (p. ej. 64px de frame a 84px de dispositivo con DPR 2.625).
  const e = 0.5;
  return {{ x: f.x + e, y: f.y + e, w: f.w - 2 * e, h: f.h - 2 * e }};
}}

export function useAtlasImage() {{
  return useImage(ATLAS_SOURCE);
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
  // Compensa el inset de rectFor: ajusta la escala para que el tamaño destino
  // (scale * framePx) no cambie pese a que el source recortado es 2e px menor.
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

// --- Modo batch imperativo (post-MVP, §11) ---
// Graba N sprites en un SkPicture con un único canvas.drawAtlas: un draw call
// por textura sin el cruce JSI por transform del path declarativo (<Atlas> +
// buffers reanimados) que penaliza en Android de gama baja (#2521/#2688).
// Los pools se mutan in-place: la grabación no aloca en estado estable.

/** Specs tipadas de solo lectura (tuplas planas, listas para grabar). */
export type SpriteSpecData = readonly (readonly [
  id: string,
  x: number,
  y: number,
  scale: number,
])[];

/** Convierte SpriteSpec[] a tuplas planas. */
export function toSpecData(
  specs: readonly SpriteSpec[],
  scale = frameScale,
): SpriteSpecData {{
  return specs.map((s) => [s.id, s.x, s.y, s.scale ?? scale]);
}}

/** Infla specs planas a pools mutables de rects/xforms listos para grabar. */
export function inflateSpecData(data: SpriteSpecData): {{
  rects: SkHostRect[];
  xforms: SkRSXform[];
}} {{
  const rects: SkHostRect[] = new Array(data.length);
  const xforms: SkRSXform[] = new Array(data.length);
  for (let i = 0; i < data.length; i++) {{
    const [id, x, y, scale] = data[i];
    const f = frameById(id);
    // Mismo inset de medio texel y compensación de escala que rectFor:
    // el destino sigue siendo scale * framePx pese al source recortado.
    const e = 0.5;
    rects[i] = Skia.XYWHRect(f.x + e, f.y + e, f.w - 2 * e, f.h - 2 * e);
    xforms[i] = Skia.RSXform(scale * (f.w / (f.w - 2 * e)), 0, x, y);
  }}
  return {{ rects, xforms }};
}}

/**
 * Graba specs estáticas en un SkPicture con un único drawAtlas.
 * `dpr` opcional: si se pasa, alinea cada sprite a píxel de dispositivo
 * (recomendado con DPR no entero y muestreo nearest, ver IslandMap).
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
 * Buffers preasignados + paint imperativo compartido para batches animados.
 * `count` fija la capacidad (reserva por una vez, sin realloc por frame);
 * `specs.length` sprites activos se escriben con `inflateInto` cada frame.
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
    /** Vuelca las primeras specs.length posiciones de los buffers. */
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
  if (!auto) throw new Error('manifest sin bloque autotile');
  const entry = auto.items[item];
  if (!entry) throw new Error(`autotile desconocido: ${{item}}`);
  const m = canonicalMask(mask, entry.size);
  const id = entry.mask[String(m)];
  if (!id) throw new Error(`autotile sin frame para máscara ${{m}} en ${{item}}`);
  return frameById(id);
}}

export function glyphFrame(char: string, item = 'font'): Frame {{
  const fontBlock = manifest.font;
  if (!fontBlock) throw new Error('manifest sin bloque font');
  const entry = fontBlock.items[item];
  if (!entry) throw new Error(`font desconocido: ${{item}}`);
  const glyph = entry.glyphs[char];
  if (!glyph) throw new Error(`glifo sin frame para caracter '${{char}}' en ${{item}}`);
  return frameById(glyph.id);
}}

/** Arma SpriteSpec[] para un texto, avanzando en x según el ancho de cada glifo. */
export function textSprites(
  text: string,
  origin: {{ x: number; y: number }},
  item = 'font',
  scale = frameScale,
): SpriteSpec[] {{
  const fontBlock = manifest.font;
  if (!fontBlock) throw new Error('manifest sin bloque font');
  const entry = fontBlock.items[item];
  if (!entry) throw new Error(`font desconocido: ${{item}}`);
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
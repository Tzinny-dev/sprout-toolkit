"""`sprout` CLI: deterministic procedural 2D asset generation for Expo.

Usage:
  sprout generate specs/demo.json --out ../demo/assets/procgen
  sprout generate specs/demo.json --png-mode png8 --texturepacker --mipmaps
  sprout generate specs/demo.json --tiers 64,128,256 --out ./tiers
  sprout generate specs/demo.json --frame-px 128 --silhouette
  sprout batch specs/ --out ../demo/assets/procgen
  sprout watch specs/ --out ../demo/assets/procgen
  sprout info specs/demo.json [--json]
  sprout lint specs/demo.json [--json]
  sprout diversity specs/demo.json [--json] [--no-fail]
  sprout diff <a> <b> [--json]
  sprout validate specs/demo.json
  sprout validate specs/demo.json --coverage catalog.ts --field key --map mapping.json
  sprout catalog catalog.ts --field key --map mapping.json --out specs/catalog.json
  sprout init --out ./assets/starter   # copy the starter spec + tutorial
"""
from __future__ import annotations

import io
import json
import time
import zlib
from pathlib import Path

import typer

from . import __version__
from . import catalog as catalog_mod
from .exporter import (
    apply_png_mode,
    blacken,
    build_autotile_map,
    build_font_map,
    build_manifest,
    build_shader,
    build_sheet,
    build_texturepacker,
    build_tier_shaders,
    compute_mipmap_meta,
    emit_index_ts,
    emit_tier_index_ts,
    render_items,
    shader_filename,
    texturepacker_filename,
    write_manifest,
    write_mipmap_files,
    write_png,
    write_texturepacker,
)
from .generators import plugin_generator_ids
from .generators.base import FrameData
from . import diversity as diversity_mod
from .spec import Layout, Spec, SpecError, load_spec

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="sprout — deterministic procedural 2D assets for Expo + react-native-skia.")


PNG_MODES = ("rgba", "png8", "png24")


def _generate(spec_path: Path, out_dir: Path | None, seed: int | None,
              skip_existing: bool, png_mode: str = "rgba",
              texturepacker: bool = False, mipmaps: bool = False,
              mip_levels: int = 3, frame_px: int | None = None,
              silhouette: bool = False) -> dict:
    spec = load_spec(spec_path)
    if seed is not None:
        spec.seed = seed
    if frame_px is not None:
        if frame_px < 8 or frame_px > 4096:
            raise SpecError(f"invalid --frame-px: {frame_px} (8..4096)")
        spec.layout.frame_px = frame_px

    frames = render_items(spec)
    sheet, records = build_sheet(spec, frames)
    out = out_dir if out_dir is not None else spec_path.parent
    atlas_name = spec.filename
    atlas_path = out / atlas_name
    manifest_path = out / "manifest.json"
    index_path = out / "index.ts"
    tp_path = out / texturepacker_filename(spec) if texturepacker else None
    sil_path = out / "silhouette.png" if silhouette else None

    autotile_map = build_autotile_map(spec, frames)
    font_map = build_font_map(spec, frames)
    shader_source, shader_block = build_shader(spec)
    shader_path = out / shader_filename(spec) if shader_block else None
    tier_shaders = build_tier_shaders(spec)
    tiers_block = (
        {name: {"file": t["file"], "template": t["template"],
                "uniforms": t["uniforms"]}
         for name, t in tier_shaders.items()}
        or None
    )
    mip_meta = compute_mipmap_meta(sheet, spec, mip_levels) if mipmaps else []
    manifest = build_manifest(spec, records, atlas_name, sheet, str(spec_path),
                              autotile_map, shader_block, font_map,
                              {"levels": mip_meta} if mip_meta else None,
                              "silhouette.png" if silhouette else None,
                              tiers_block)

    if skip_existing and atlas_path.is_file() and manifest_path.is_file() and index_path.is_file():
        missing_extra = (
            (shader_block and not (shader_path and shader_path.is_file()))
            or any(not (out / t["file"]).is_file() for t in tier_shaders.values())
            or (texturepacker and not tp_path.is_file())
            or (silhouette and not (sil_path and sil_path.is_file()))
            or (mipmaps and not all((out / lvl["file"]).is_file() for lvl in mip_meta))
        )
        if missing_extra:
            pass  # an optional artifact is missing -> regenerate
        else:
            current = zlib.crc32(atlas_path.read_bytes()) & 0xFFFFFFFF
            probe = io.BytesIO()
            apply_png_mode(sheet, png_mode).save(probe, format="PNG")
            fresh = zlib.crc32(probe.getvalue()) & 0xFFFFFFFF
            same_manifest = manifest_path.read_bytes() == (
                json.dumps(manifest, indent=2) + "\n"
            ).encode()
            same_shader = (
                shader_source is None
                or (shader_path is not None
                    and shader_path.read_bytes() == shader_source.encode())
            )
            same_tiers = all(
                (out / t["file"]).read_text() == t["source"]
                for t in tier_shaders.values()
            )
            if current == fresh and same_manifest and same_shader and same_tiers:
                return {"spec": spec, "out": out, "atlas": atlas_path,
                        "crc": current, "skipped": True, "manifest": manifest}

    crc = write_png(sheet, atlas_path, png_mode)
    if sil_path is not None:
        write_png(blacken(sheet), sil_path, "rgba")
    write_manifest(manifest, manifest_path)
    if shader_source is not None and shader_path is not None:
        shader_path.parent.mkdir(parents=True, exist_ok=True)
        shader_path.write_text(shader_source)
    for t in tier_shaders.values():
        (out / t["file"]).write_text(t["source"])
    emit_index_ts(manifest, index_path)
    if texturepacker:
        tp = build_texturepacker(spec, records, atlas_name, sheet, png_mode)
        write_texturepacker(tp, tp_path)
    if mipmaps:
        write_mipmap_files(sheet, out, png_mode, mip_meta)
    return {"spec": spec, "out": out, "atlas": atlas_path, "crc": crc,
            "skipped": False, "manifest": manifest}


STARTER_SPEC = """{
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
"""


@app.command()
def init(
    out: Path = typer.Option(Path("./assets/starter"), "--out", "-o",
                             help="directory for the starter spec + generated assets"),
    generate_now: bool = typer.Option(True, "--generate/--no-generate",
                                      help="run generate right after writing the spec"),
) -> None:
    """Write a starter spec and generate its atlas (pip-first onboarding)."""
    out.mkdir(parents=True, exist_ok=True)
    spec_path = out / "starter.json"
    if not spec_path.is_file():
        spec_path.write_text(STARTER_SPEC)
        typer.secho(f"wrote {spec_path.resolve()}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"keep existing {spec_path.resolve()}", fg=typer.colors.YELLOW)
    if generate_now:
        r = _generate(spec_path, out, None, False, "rgba", False, False, 3)
        s: Spec = r["spec"]
        typer.secho(
            f"[{s.name}] seed={s.seed} frames={s.total_frames} "
            f"sheet={s.layout.cols}x{s.layout.resolve_rows(s.total_frames)} grid"
            f" -> {r['out'].resolve()}",
            fg=typer.colors.GREEN,
        )
        typer.secho(f"  atlas.png crc=0x{r['crc']:08x}", fg=typer.colors.BRIGHT_BLACK)
    typer.echo("next: see docs/starter-tutorial.md (10-minute Expo walkthrough)")


def _parse_tiers(tiers: str) -> list[int]:
    try:
        px = sorted({int(p.strip()) for p in tiers.split(",") if p.strip()})
    except ValueError:
        px = []
    if not px or any(p < 8 or p > 4096 for p in px):
        raise typer.BadParameter(
            f"invalid --tiers '{tiers}' (comma-separated px, each 8..4096)")
    return px


@app.command()
def generate(
    spec: Path = typer.Argument(..., help="spec.json to generate"),
    out: Path = typer.Option(None, "--out", "-o", help="output directory (default: next to the spec)"),
    seed: int = typer.Option(None, "--seed", "-s", help=f"override the spec's seed"),
    skip_existing: bool = typer.Option(False, "--skip-existing", help="skip rewriting if the atlas already exists with the same crc"),
    png_mode: str = typer.Option("rgba", "--png-mode", help="atlas format: rgba | png8 | png24"),
    texturepacker: bool = typer.Option(False, "--texturepacker", help="also emit <name>.tpsheet.json (TexturePacker JSON Hash format)"),
    mipmaps: bool = typer.Option(False, "--mipmaps", help="generate a chain of atlas mip levels (@0.5x, @0.25x, ...)"),
    mipmap_levels: int = typer.Option(3, "--mipmap-levels", help="maximum number of mip levels (with --mipmaps)"),
    frame_px: int = typer.Option(None, "--frame-px", help="override layout.framePx (single-resolution output)"),
    silhouette: bool = typer.Option(False, "--silhouette", help="also emit silhouette.png (black x alpha) + SILHOUETTE_SOURCE"),
    tiers: str = typer.Option(None, "--tiers", help="one atlas per px size, e.g. 64,128,256 — subdirs + combined index.ts"),
) -> None:
    """Generate spritesheet + manifest.json + index.ts from a spec."""
    if png_mode not in PNG_MODES:
        typer.secho(f"invalid --png-mode '{png_mode}' (available: {', '.join(PNG_MODES)})",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if tiers and frame_px is not None:
        typer.secho("--tiers and --frame-px are mutually exclusive",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if tiers:
        px_list = _parse_tiers(tiers)
        dest = out if out is not None else spec.parent
        results: list[tuple[int, dict]] = []
        try:
            for px in px_list:
                r = _generate(spec, dest / str(px), seed, skip_existing,
                              png_mode, texturepacker, mipmaps, mipmap_levels,
                              frame_px=px, silhouette=silhouette)
                results.append((px, r["manifest"]))
        except SpecError as e:
            typer.secho(f"error in {spec}: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        emit_tier_index_ts(dest, results)
        typer.secho(
            f"[{spec.stem}] tiers {', '.join(str(p) for p in px_list)} -> "
            f"{dest.resolve()} (index.ts: atlasSources, pickTier)",
            fg=typer.colors.GREEN,
        )
        return
    try:
        r = _generate(spec, out, seed, skip_existing, png_mode, texturepacker,
                      mipmaps, mipmap_levels, frame_px=frame_px,
                      silhouette=silhouette)
    except SpecError as e:
        typer.secho(f"error in {spec}: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    s: Spec = r["spec"]
    if r["skipped"]:
        typer.secho(f"[{s.name}] no changes (crc {r['crc']:08x}) — skip", fg=typer.colors.YELLOW)
        return
    typer.secho(
        f"[{s.name}] seed={s.seed} frames={s.total_frames} "
        f"sheet={s.layout.cols}x{s.layout.resolve_rows(s.total_frames)} grid"
        f" -> {r['out'].resolve()}",
        fg=typer.colors.GREEN,
    )
    typer.secho(f"  atlas.png crc=0x{r['crc']:08x}", fg=typer.colors.BRIGHT_BLACK)


@app.command()
def batch(
    specs_dir: Path = typer.Argument(..., help="directory (or glob) with specs"),
    out: Path = typer.Option(None, "--out", "-o", help="common output directory"),
    skip_existing: bool = typer.Option(False, "--skip-existing", help="skip rewriting atlases without changes"),
    png_mode: str = typer.Option("rgba", "--png-mode", help="atlas format: rgba | png8 | png24"),
    texturepacker: bool = typer.Option(False, "--texturepacker", help="also emit <name>.tpsheet.json (TexturePacker JSON Hash format)"),
    mipmaps: bool = typer.Option(False, "--mipmaps", help="generate a chain of atlas mip levels (@0.5x, @0.25x, ...)"),
    mipmap_levels: int = typer.Option(3, "--mipmap-levels", help="maximum number of mip levels (with --mipmaps)"),
    silhouette: bool = typer.Option(False, "--silhouette", help="also emit silhouette.png (black x alpha) + SILHOUETTE_SOURCE"),
) -> None:
    """Generate every spec in a directory (*.json pattern)."""
    if png_mode not in PNG_MODES:
        typer.secho(f"invalid --png-mode '{png_mode}' (available: {', '.join(PNG_MODES)})",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    files = sorted(specs_dir.glob("*.json"))
    if not files:
        typer.secho(f"no specs (*.json) found in {specs_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    failed = 0
    for f in files:
        try:
            _generate(f, out, None, skip_existing, png_mode, texturepacker,
                      mipmaps, mipmap_levels, silhouette=silhouette)
        except SpecError as e:
            typer.secho(f"error in {f}: {e}", fg=typer.colors.RED, err=True)
            failed += 1
    typer.echo(f"[batch] {len(files) - failed}/{len(files)} specs ok")
    if failed:
        raise typer.Exit(1)


@app.command()
def validate(
    spec: Path = typer.Argument(..., help="spec.json to validate"),
    coverage_file: Path = typer.Option(None, "--coverage",
                                       help="catalog file: fail if any id has no frame"),
    field: str = typer.Option(None, "--field",
                              help="id field in the coverage catalog"),
    map_path: Path = typer.Option(None, "--map",
                                  help="mapping.json (its 'skip' ids are excluded)"),
) -> None:
    """Validate a spec's structure, plugins, and catalog coverage."""
    try:
        s = load_spec(spec)
    except SpecError as e:
        typer.secho(f"invalid: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if coverage_file is not None and field is None:
        typer.secho("--field is required with --coverage",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if coverage_file is not None:
        try:
            mapping = catalog_mod.load_mapping(map_path)
            expected, missing = catalog_mod.coverage(
                spec, coverage_file, field, mapping=mapping)
        except catalog_mod.CatalogError as e:
            typer.secho(f"coverage error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        if missing:
            shown = ", ".join(missing[:10])
            extra = f" (+{len(missing) - 10} more)" if len(missing) > 10 else ""
            typer.secho(
                f"coverage {len(expected) - len(missing)}/{len(expected)} — "
                f"missing frames: {shown}{extra}",
                fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        typer.secho(f"coverage {len(expected)}/{len(expected)}",
                    fg=typer.colors.GREEN)
    typer.secho(
        f"[{s.name}] OK — items={[i.id for i in s.items]} "
        f"frames={s.total_frames} seed={s.seed}",
        fg=typer.colors.GREEN,
    )


@app.command()
def catalog(
    file: Path = typer.Argument(...,
                                help="catalog file (.json or .ts) to extract ids from"),
    field: str = typer.Option(..., "--field",
                              help="record field carrying the unique id"),
    map_path: Path = typer.Option(None, "--map",
                                  help="mapping.json: sets/ids → generator + params"),
    generator: str = typer.Option(None, "--generator",
                                  help="fallback generator when no --map is given"),
    set_field: str = typer.Option("set", "--set-field",
                                  help="record field carrying the set name"),
    out: Path = typer.Option(None, "--out", "-o",
                             help="output spec path (default: specs/<name>.json)"),
    name: str = typer.Option(None, "--name",
                             help="spec name (default: <file stem>_catalog)"),
    seed: int = typer.Option(0, "--seed", help="spec seed"),
    frame_px: int = typer.Option(64, "--frame-px", help="frame size in px"),
) -> None:
    """Emit a spec from a catalog file + an external mapping.json."""
    try:
        records = catalog_mod.extract_records(file, field)
        mapping = catalog_mod.load_mapping(map_path)
        items = catalog_mod.resolve_items(
            records, field, mapping, set_field=set_field,
            fallback_generator=generator)
    except catalog_mod.CatalogError as e:
        typer.secho(f"catalog error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    spec_name = name or f"{file.stem}_catalog"
    spec = catalog_mod.build_spec(items, name=spec_name, seed=seed,
                                  frame_px=frame_px)
    dest = out or (Path("specs") / f"{spec_name}.json")
    catalog_mod.write_spec(spec, dest)
    typer.secho(f"[catalog] {len(items)} ids -> {dest}", fg=typer.colors.GREEN)


@app.command()
def info(
    spec: Path = typer.Argument(..., help="spec.json to inspect"),
    as_json: bool = typer.Option(False, "--json", help="machine-readable output"),
) -> None:
    """Report on a spec: items, frames, layout, and estimated atlas size."""
    try:
        s = load_spec(spec)
    except SpecError as e:
        typer.secho(f"invalid: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    cols = s.layout.cols
    rows = s.layout.resolve_rows(s.total_frames)
    fpx = s.layout.frame_px
    atlas_w, atlas_h = cols * fpx, rows * fpx

    if as_json:
        typer.echo(json.dumps({
            "name": s.name,
            "seed": s.seed,
            "target": s.target,
            "spec": str(spec),
            "layout": {
                "framePx": fpx, "cols": cols, "rows": rows,
                "tileLogical": s.layout.tile_logical, "sample": s.layout.sample,
            },
            "atlas": {
                "file": s.filename, "width": atlas_w, "height": atlas_h,
                "frames": s.total_frames,
            },
            "items": [
                {"id": it.id, "generator": it.generator, "frames": it.frames,
                 "autotile": it.autotile, "params": it.params}
                for it in s.items
            ],
            "animations": {
                n: {"frames": a.frames, "fps": a.fps, "loop": a.loop}
                for n, a in s.animations.items()
            },
            "runtime": bool(s.runtime),
        }, indent=2))
        return

    typer.secho(f"[{s.name}] {spec}", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  seed    : {s.seed}")
    typer.echo(f"  target  : {s.target}")
    typer.echo(f"  layout  : framePx={fpx} cols={cols} rows={rows} "
               f"tileLogical={s.layout.tile_logical} sample={s.layout.sample}")
    typer.echo(f"  atlas   : {s.filename} {atlas_w}x{atlas_h} ({s.total_frames} frames)")
    typer.echo(f"  runtime : {'yes' if s.runtime else 'no'}")
    plug_ids = plugin_generator_ids()
    if plug_ids:
        typer.echo(f"  plugins : {', '.join(plug_ids)}")
    typer.echo("  items:")
    for it in s.items:
        extra = ""
        if it.autotile:
            extra += f" autotile={it.autotile}"
        keys = sorted(k for k in it.params if k != "autotile")
        if keys:
            extra += f" params[{','.join(keys)}]"
        typer.echo(f"    - {it.id:<14} {it.generator:<10} frames={it.frames}{extra}")
    if s.animations:
        typer.echo("  anim:")
        for name, a in s.animations.items():
            typer.echo(f"    - {name:<14} frames={a.frames} fps={a.fps} loop={a.loop}")


@app.command()
def diversity(
    spec: Path = typer.Argument(..., help="spec.json to analyze"),
    as_json: bool = typer.Option(False, "--json", help="machine-readable output"),
    fail: bool = typer.Option(
        True, "--fail/--no-fail",
        help="exit 1 when two items share the same form"),
) -> None:
    """Measure form coverage: which items share the same form params.

    Groups items by generator, frame count, autotile and structural
    params, dropping palettes, colour literals and the tint declaration
    first — items differing only in colour are one form recoloured. Two
    items that agree on all of it are a coverage gap, since the effective
    vocabulary is smaller than the catalog says.
    """
    try:
        s = load_spec(spec)
    except SpecError as e:
        typer.secho(f"invalid: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    groups = diversity_mod.diversity_groups(s.items)
    distinct = diversity_mod.distinct_forms(s.items)
    total = len(s.items)

    if as_json:
        typer.echo(json.dumps({
            "spec": str(spec),
            "items": total,
            "distinct_forms": distinct,
            "collisions": [
                {"items": members} for members in groups
            ],
        }, indent=2))
    elif not groups:
        msg = (f"[{s.name}] OK — {total} items, {distinct} distinct forms, "
               f"no collisions")
        typer.secho(msg, fg=typer.colors.GREEN)
    else:
        msg = (f"[{s.name}] {total} items, {distinct} distinct forms, "
               f"{len(groups)} collision(s):")
        typer.secho(msg, fg=typer.colors.YELLOW)
        for members in groups:
            typer.echo(f"  - {', '.join(members)}")
    raise typer.Exit(1 if fail and groups else 0)


PADDING_WARN_RATIO = 0.25
DEFAULT_MAX_ATLAS_MB = 16.0


def _lint_warnings(spec: Spec, items_frames: list[list[FrameData]],
                   max_atlas_bytes: int = int(DEFAULT_MAX_ATLAS_MB * (1 << 20))) -> list[dict]:
    """Quality warnings for an already-rendered spec: atlas padding,
    completely transparent frames and atlas size vs. the bundle budget."""
    warnings: list[dict] = []

    cols = spec.layout.cols
    rows = spec.layout.resolve_rows(spec.total_frames)
    capacity = cols * rows
    unused = capacity - spec.total_frames
    if capacity and unused / capacity > PADDING_WARN_RATIO:
        warnings.append({
            "check": "padding",
            "message": f"{unused}/{capacity} unused atlas cells ({unused / capacity:.0%})",
        })

    if max_atlas_bytes > 0:
        atlas_bytes = capacity * spec.layout.frame_px * spec.layout.frame_px * 4
        if atlas_bytes > max_atlas_bytes:
            warnings.append({
                "check": "atlas_size",
                "message": (
                    f"atlas is {atlas_bytes / (1 << 20):.1f} MB uncompressed (RGBA) "
                    f"over the {max_atlas_bytes / (1 << 20):.0f} MB budget — "
                    f"consider --png-mode png8 or a lower layout.framePx"
                ),
                "bytes": atlas_bytes,
            })

    empty_ids = [
        fr.id
        for item, frames in zip(spec.items, items_frames, strict=True)
        # the `font` generator produces empty glyphs on purpose (the space
        # character paints no pixels) — not a wasted frame.
        if item.generator != "font"
        for fr in frames
        # RGB tiles (e.g. terrain without autotile) are opaque by design
        # and have no alpha channel to check.
        if fr.image.mode == "RGBA" and fr.image.getchannel("A").getbbox() is None
    ]
    if empty_ids:
        warnings.append({
            "check": "empty_frames",
            "message": f"{len(empty_ids)} completely transparent frame(s)",
            "ids": empty_ids,
        })

    return warnings


@app.command()
def lint(
    spec: Path = typer.Argument(..., help="spec.json to analyze"),
    as_json: bool = typer.Option(False, "--json", help="machine-readable output"),
    max_atlas_mb: float = typer.Option(
        DEFAULT_MAX_ATLAS_MB, "--max-atlas-mb",
        help="warn when the atlas exceeds this uncompressed RGBA budget in MB (0 disables)"),
) -> None:
    """Analyze a spec: atlas padding, empty frames and size budget (renders to verify)."""
    try:
        s = load_spec(spec)
        items_frames = render_items(s)
    except SpecError as e:
        typer.secho(f"invalid: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    warnings = _lint_warnings(s, items_frames, int(max_atlas_mb * (1 << 20)))
    if as_json:
        typer.echo(json.dumps({"spec": str(spec), "warnings": warnings}, indent=2))
    elif not warnings:
        typer.secho(f"[{s.name}] OK — no warnings", fg=typer.colors.GREEN)
    else:
        typer.secho(f"[{s.name}] {len(warnings)} warning(s):", fg=typer.colors.YELLOW)
        for w in warnings:
            typer.echo(f"  - [{w['check']}] {w['message']}")
    raise typer.Exit(1 if warnings else 0)


def _diff_specs(a: Spec, b: Spec) -> list[dict]:
    """Structural differences between two specs: `[{"field", "a", "b"}, ...]`."""
    diffs: list[dict] = []

    for field in ("name", "seed", "target"):
        av, bv = getattr(a, field), getattr(b, field)
        if av != bv:
            diffs.append({"field": field, "a": av, "b": bv})

    a_colors = [(c.key, c.hex) for c in a.colors]
    b_colors = [(c.key, c.hex) for c in b.colors]
    if a_colors != b_colors:
        diffs.append({"field": "colors", "a": a_colors, "b": b_colors})

    for f in ("frame_px", "cols", "tile_logical", "sample"):
        av, bv = getattr(a.layout, f), getattr(b.layout, f)
        if av != bv:
            diffs.append({"field": f"layout.{f}", "a": av, "b": bv})

    a_items = {i.id: i for i in a.items}
    b_items = {i.id: i for i in b.items}
    for iid in sorted(set(b_items) - set(a_items)):
        diffs.append({"field": f"items.{iid}", "a": None, "b": "added"})
    for iid in sorted(set(a_items) - set(b_items)):
        diffs.append({"field": f"items.{iid}", "a": "removed", "b": None})
    for iid in sorted(set(a_items) & set(b_items)):
        ia, ib = a_items[iid], b_items[iid]
        if ((ia.generator, ia.frames, ia.params, ia.tint)
                != (ib.generator, ib.frames, ib.params, ib.tint)):
            diffs.append({
                "field": f"items.{iid}",
                "a": {"generator": ia.generator, "frames": ia.frames,
                      "params": ia.params, "tint": ia.tint},
                "b": {"generator": ib.generator, "frames": ib.frames,
                      "params": ib.params, "tint": ib.tint},
            })

    a_anim, b_anim = a.animations, b.animations
    for name in sorted(set(b_anim) - set(a_anim)):
        diffs.append({"field": f"animations.{name}", "a": None, "b": "added"})
    for name in sorted(set(a_anim) - set(b_anim)):
        diffs.append({"field": f"animations.{name}", "a": "removed", "b": None})
    for name in sorted(set(a_anim) & set(b_anim)):
        ia, ib = a_anim[name], b_anim[name]
        if (ia.frames, ia.fps, ia.loop) != (ib.frames, ib.fps, ib.loop):
            diffs.append({
                "field": f"animations.{name}",
                "a": {"frames": ia.frames, "fps": ia.fps, "loop": ia.loop},
                "b": {"frames": ib.frames, "fps": ib.fps, "loop": ib.loop},
            })

    return diffs


def _diff_outputs(a: Path, b: Path) -> list[dict]:
    """Differences between two output directories: atlas CRC + manifest.json."""
    diffs: list[dict] = []

    atlas_a, atlas_b = a / "atlas.png", b / "atlas.png"
    if atlas_a.is_file() and atlas_b.is_file():
        crc_a = zlib.crc32(atlas_a.read_bytes()) & 0xFFFFFFFF
        crc_b = zlib.crc32(atlas_b.read_bytes()) & 0xFFFFFFFF
        if crc_a != crc_b:
            diffs.append({"field": "atlas.crc", "a": f"{crc_a:08x}", "b": f"{crc_b:08x}"})
    else:
        diffs.append({"field": "atlas.png", "a": atlas_a.is_file(), "b": atlas_b.is_file()})

    man_a_p, man_b_p = a / "manifest.json", b / "manifest.json"
    if not (man_a_p.is_file() and man_b_p.is_file()):
        diffs.append({"field": "manifest.json", "a": man_a_p.is_file(), "b": man_b_p.is_file()})
        return diffs

    man_a = json.loads(man_a_p.read_text())
    man_b = json.loads(man_b_p.read_text())

    for field in ("name", "seed"):
        if man_a.get(field) != man_b.get(field):
            diffs.append({"field": field, "a": man_a.get(field), "b": man_b.get(field)})

    size_a = (man_a["files"]["atlasW"], man_a["files"]["atlasH"])
    size_b = (man_b["files"]["atlasW"], man_b["files"]["atlasH"])
    if size_a != size_b:
        diffs.append({"field": "atlas.size", "a": list(size_a), "b": list(size_b)})

    ids_a = {f["id"] for f in man_a["frames"]}
    ids_b = {f["id"] for f in man_b["frames"]}
    if ids_b - ids_a:
        diffs.append({"field": "frames.added", "a": None, "b": sorted(ids_b - ids_a)})
    if ids_a - ids_b:
        diffs.append({"field": "frames.removed", "a": sorted(ids_a - ids_b), "b": None})

    for block in ("autotile", "shader", "font", "tint"):
        if (block in man_a) != (block in man_b):
            diffs.append({"field": f"{block}.present", "a": block in man_a, "b": block in man_b})

    return diffs


@app.command()
def diff(
    a: Path = typer.Argument(..., help="spec.json or output directory A"),
    b: Path = typer.Argument(..., help="spec.json or output directory B"),
    as_json: bool = typer.Option(False, "--json", help="machine-readable output"),
) -> None:
    """Compare two specs (.json) or two output directories (atlas+manifest)."""
    a_is_spec, b_is_spec = a.suffix == ".json", b.suffix == ".json"
    if a_is_spec != b_is_spec:
        typer.secho("cannot compare a spec (.json) with an output directory",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    try:
        if a_is_spec:
            kind, diffs = "spec", _diff_specs(load_spec(a), load_spec(b))
        else:
            if not a.is_dir() or not b.is_dir():
                typer.secho(f"directory not found: {a if not a.is_dir() else b}",
                            fg=typer.colors.RED, err=True)
                raise typer.Exit(1)
            kind, diffs = "output", _diff_outputs(a, b)
    except SpecError as e:
        typer.secho(f"invalid: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    if as_json:
        typer.echo(json.dumps({"a": str(a), "b": str(b), "kind": kind, "diffs": diffs}, indent=2))
    elif not diffs:
        typer.secho(f"no differences ({kind})", fg=typer.colors.GREEN)
    else:
        typer.secho(f"{len(diffs)} difference(s) ({kind}):", fg=typer.colors.YELLOW)
        for d in diffs:
            typer.echo(f"  - {d['field']}: {d['a']!r} -> {d['b']!r}")
    raise typer.Exit(1 if diffs else 0)


@app.command()
def watch(
    specs_dir: Path = typer.Argument(..., help="directory with specs (*.json)"),
    out: Path = typer.Option(None, "--out", "-o", help="output directory (default: next to each spec)"),
    interval: float = typer.Option(1.0, "--interval", "-i", help="change-polling interval in seconds"),
) -> None:
    """Watch specs/ and regenerate assets when they change (Ctrl-C to stop)."""
    if not specs_dir.is_dir():
        typer.secho(f"directory does not exist: {specs_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    files = sorted(specs_dir.glob("*.json"))
    if not files:
        typer.secho(f"no specs (*.json) found in {specs_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    typer.secho(
        f"[watch] {specs_dir} -> {out or specs_dir} every {interval}s "
        f"({len(files)} specs) — Ctrl-C to exit",
        fg=typer.colors.CYAN,
    )
    mtimes: dict[Path, float] = {}
    first = True
    try:
        while True:
            for f in sorted(specs_dir.glob("*.json")):
                try:
                    mt = f.stat().st_mtime
                except OSError:
                    continue
                if mtimes.get(f, 0.0) >= mt:
                    continue
                mtimes[f] = mt
                if not first:
                    typer.secho(f"  [changed] {f.name}", fg=typer.colors.BLUE)
                try:
                    r = _generate(f, out, None, True)
                except SpecError as e:
                    typer.secho(f"  [error] {f.name}: {e}", fg=typer.colors.RED, err=True)
                    continue
                s: Spec = r["spec"]
                if r["skipped"]:
                    typer.secho(f"  [skip]  {s.name} no changes (crc {r['crc']:08x})",
                                fg=typer.colors.YELLOW)
                else:
                    typer.secho(
                        f"  [ok]    {s.name} seed={s.seed} frames={s.total_frames} "
                        f"-> {r['out'].resolve()} (crc {r['crc']:08x})",
                        fg=typer.colors.GREEN,
                    )
            first = False
            time.sleep(interval)
    except KeyboardInterrupt:
        typer.secho("\n[watch] stopped.", fg=typer.colors.CYAN)


@app.command("import")
def import_cmd(
    src: Path = typer.Argument(..., help="directory of loose PNG frames (top-level *.png, uniform size)"),
    out: Path = typer.Option(..., "--out", "-o", help="output directory (atlas + manifest + index.ts)"),
    name: str = typer.Option(None, "--name", help="atlas name (default: <dir>_atlas)"),
    seed: int = typer.Option(0, "--seed", help="manifest seed (informational)"),
    cols: int = typer.Option(8, "--cols", help="spritesheet grid columns"),
) -> None:
    """Pack a directory of loose PNGs into atlas + manifest + index.ts."""
    if not src.is_dir():
        typer.secho(f"not a directory: {src}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if cols < 1 or cols > 512:
        typer.secho(f"invalid --cols: {cols} (1..512)", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    files = sorted(src.glob("*.png"))
    if not files:
        typer.secho(f"no *.png frames found in {src}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    from PIL import Image, UnidentifiedImageError

    sizes: set[tuple[int, int]] = set()
    images: list[tuple[str, Image.Image]] = []
    for f in files:
        stem = f.stem
        if not stem or not stem.replace("_", "").replace("-", "").isalnum():
            typer.secho(
                f"invalid frame id '{stem}' (alphanumeric, '_' and '-' only)",
                fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        try:
            img = Image.open(f).convert("RGBA")
            img.load()
        except (UnidentifiedImageError, OSError) as e:
            typer.secho(f"unreadable PNG {f.name}: {e}",
                        fg=typer.colors.RED, err=True)
            raise typer.Exit(1)
        sizes.add(img.size)
        images.append((stem, img))

    if len(sizes) > 1:
        found = ", ".join(f"{w}x{h}" for w, h in sorted(sizes))
        typer.secho(
            f"frames must all share one size (found: {found})",
            fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    frame_w, frame_h = sizes.pop()
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in src.name)
    spec_name = name or f"{safe}_atlas"
    if not spec_name.replace("_", "").replace("-", "").isalnum():
        typer.secho(f"invalid --name '{spec_name}' (alphanumeric, '_' and '-' only)",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    cols_used = min(cols, len(images))
    rows = -(-len(images) // cols_used)
    sheet = Image.new("RGBA", (cols_used * frame_w, rows * frame_h), (0, 0, 0, 0))
    records: list[dict] = []
    for i, (stem, img) in enumerate(images):
        col, row = i % cols_used, i // cols_used
        x, y = col * frame_w, row * frame_h
        sheet.paste(img, (x, y), img)
        records.append({"id": stem, "col": col, "row": row,
                        "x": x, "y": y, "w": frame_w, "h": frame_h})

    spec = Spec(
        name=spec_name, seed=seed, items=[], animations={},
        layout=Layout(frame_px=frame_w, cols=cols_used,
                      tile_logical=frame_w, sample="nearest"),
        files_atlas="atlas.png",
    )
    manifest = build_manifest(spec, records, "atlas.png", sheet, str(src))
    write_png(sheet, out / "atlas.png", "rgba")
    write_manifest(manifest, out / "manifest.json")
    emit_index_ts(manifest, out / "index.ts")
    typer.secho(
        f"[{spec_name}] {len(records)} frames ({frame_w}x{frame_h}) -> "
        f"{out.resolve()}",
        fg=typer.colors.GREEN,
    )


@app.callback(invoke_without_command=True)
def _version(version: bool = typer.Option(False, "--version", help="show the version")) -> None:
    if version:
        typer.echo(f"sprout {__version__}")
        raise typer.Exit()


if __name__ == "__main__":
    app()

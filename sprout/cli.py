"""CLI `sprout`: generación procedural determinista de assets 2D para Expo.

Uso:
  sprout generate specs/demo.json --out ../demo/assets/procgen
  sprout batch specs/ --out ../demo/assets/procgen
  sprout watch specs/ --out ../demo/assets/procgen
  sprout info specs/demo.json [--json]
  sprout lint specs/demo.json [--json]
  sprout validate specs/demo.json
"""
from __future__ import annotations

import io
import json
import time
import zlib
from pathlib import Path

import typer

from . import __version__
from .exporter import (
    build_autotile_map,
    build_manifest,
    build_shader,
    build_sheet,
    emit_index_ts,
    render_items,
    shader_filename,
    write_manifest,
    write_png,
)
from .generators.base import FrameData
from .spec import Spec, SpecError, load_spec

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="sprout — assets 2D procedurales deterministas para Expo + react-native-skia.")


def _generate(spec_path: Path, out_dir: Path | None, seed: int | None,
              skip_existing: bool) -> dict:
    spec = load_spec(spec_path)
    if seed is not None:
        spec.seed = seed

    frames = render_items(spec)
    sheet, records = build_sheet(spec, frames)
    out = out_dir if out_dir is not None else spec_path.parent
    atlas_name = spec.filename
    atlas_path = out / atlas_name
    manifest_path = out / "manifest.json"
    index_path = out / "index.ts"

    autotile_map = build_autotile_map(spec, frames)
    shader_source, shader_block = build_shader(spec)
    shader_path = out / shader_filename(spec) if shader_block else None
    manifest = build_manifest(spec, records, atlas_name, sheet, str(spec_path),
                              autotile_map, shader_block)

    if skip_existing and atlas_path.is_file() and manifest_path.is_file() and index_path.is_file():
        if shader_block and not (shader_path and shader_path.is_file()):
            pass  # falta el .sksl -> regenerar
        else:
            current = zlib.crc32(atlas_path.read_bytes()) & 0xFFFFFFFF
            probe = io.BytesIO()
            sheet.save(probe, format="PNG")
            fresh = zlib.crc32(probe.getvalue()) & 0xFFFFFFFF
            same_manifest = manifest_path.read_bytes() == (
                json.dumps(manifest, indent=2) + "\n"
            ).encode()
            same_shader = (
                shader_source is None
                or (shader_path is not None
                    and shader_path.read_bytes() == shader_source.encode())
            )
            if current == fresh and same_manifest and same_shader:
                return {"spec": spec, "out": out, "atlas": atlas_path, "crc": current,
                        "skipped": True}

    crc = write_png(sheet, atlas_path)
    write_manifest(manifest, manifest_path)
    if shader_source is not None and shader_path is not None:
        shader_path.parent.mkdir(parents=True, exist_ok=True)
        shader_path.write_text(shader_source)
    emit_index_ts(manifest, index_path)
    return {"spec": spec, "out": out, "atlas": atlas_path, "crc": crc, "skipped": False}


@app.command()
def generate(
    spec: Path = typer.Argument(..., help="spec.json a generar"),
    out: Path = typer.Option(None, "--out", "-o", help="directorio de salida (default: junto a la spec)"),
    seed: int = typer.Option(None, "--seed", "-s", help=f"sobreescribe el seed de la spec"),
    skip_existing: bool = typer.Option(False, "--skip-existing", help="no reescribe si el atlas ya existe con el mismo crc"),
) -> None:
    """Genera spritesheet + manifest.json + index.ts desde una spec."""
    try:
        r = _generate(spec, out, seed, skip_existing)
    except SpecError as e:
        typer.secho(f"error en {spec}: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    s: Spec = r["spec"]
    if r["skipped"]:
        typer.secho(f"[{s.name}] sin cambios (crc {r['crc']:08x}) — skip", fg=typer.colors.YELLOW)
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
    specs_dir: Path = typer.Argument(..., help="directorio (o glob) con specs"),
    out: Path = typer.Option(None, "--out", "-o", help="directorio de salida común"),
    skip_existing: bool = typer.Option(False, "--skip-existing", help="no reescribe atlases sin cambios"),
) -> None:
    """Genera todas las specs de un directorio (patrón *.json)."""
    files = sorted(specs_dir.glob("*.json"))
    if not files:
        typer.secho(f"no hay specs (*.json) en {specs_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    failed = 0
    for f in files:
        try:
            _generate(f, out, None, skip_existing)
        except SpecError as e:
            typer.secho(f"error en {f}: {e}", fg=typer.colors.RED, err=True)
            failed += 1
    typer.echo(f"[batch] {len(files) - failed}/{len(files)} specs ok")
    if failed:
        raise typer.Exit(1)


@app.command()
def validate(spec: Path = typer.Argument(..., help="spec.json a validar")) -> None:
    """Valida la estructura y los plug-ins de una spec."""
    try:
        s = load_spec(spec)
    except SpecError as e:
        typer.secho(f"inválida: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.secho(
        f"[{s.name}] OK — items={[i.id for i in s.items]} "
        f"frames={s.total_frames} seed={s.seed}",
        fg=typer.colors.GREEN,
    )


@app.command()
def info(
    spec: Path = typer.Argument(..., help="spec.json a inspeccionar"),
    as_json: bool = typer.Option(False, "--json", help="salida machine-readable"),
) -> None:
    """Reporte de una spec: items, frames, layout y tamaño estimado del atlas."""
    try:
        s = load_spec(spec)
    except SpecError as e:
        typer.secho(f"inválida: {e}", fg=typer.colors.RED, err=True)
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
    typer.echo(f"  runtime : {'sí' if s.runtime else 'no'}")
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


PADDING_WARN_RATIO = 0.25


def _lint_warnings(spec: Spec, items_frames: list[list[FrameData]]) -> list[dict]:
    """Advertencias de calidad de una spec ya renderizada: padding de atlas
    (celdas de grilla sin usar) y frames completamente transparentes."""
    warnings: list[dict] = []

    cols = spec.layout.cols
    rows = spec.layout.resolve_rows(spec.total_frames)
    capacity = cols * rows
    unused = capacity - spec.total_frames
    if capacity and unused / capacity > PADDING_WARN_RATIO:
        warnings.append({
            "check": "padding",
            "message": f"{unused}/{capacity} celdas del atlas sin usar ({unused / capacity:.0%})",
        })

    empty_ids = [
        fr.id for frames in items_frames for fr in frames
        # los tiles RGB (p. ej. terrain sin autotile) son opacos por diseño
        # y no tienen canal alpha que consultar.
        if fr.image.mode == "RGBA" and fr.image.getchannel("A").getbbox() is None
    ]
    if empty_ids:
        warnings.append({
            "check": "empty_frames",
            "message": f"{len(empty_ids)} frame(s) completamente transparentes",
            "ids": empty_ids,
        })

    return warnings


@app.command()
def lint(
    spec: Path = typer.Argument(..., help="spec.json a analizar"),
    as_json: bool = typer.Option(False, "--json", help="salida machine-readable"),
) -> None:
    """Analiza una spec: padding de atlas y frames vacíos (renderiza para verificar)."""
    try:
        s = load_spec(spec)
        items_frames = render_items(s)
    except SpecError as e:
        typer.secho(f"inválida: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    warnings = _lint_warnings(s, items_frames)
    if as_json:
        typer.echo(json.dumps({"spec": str(spec), "warnings": warnings}, indent=2))
    elif not warnings:
        typer.secho(f"[{s.name}] OK — sin advertencias", fg=typer.colors.GREEN)
    else:
        typer.secho(f"[{s.name}] {len(warnings)} advertencia(s):", fg=typer.colors.YELLOW)
        for w in warnings:
            typer.echo(f"  - [{w['check']}] {w['message']}")
    raise typer.Exit(1 if warnings else 0)


@app.command()
def watch(
    specs_dir: Path = typer.Argument(..., help="directorio con specs (*.json)"),
    out: Path = typer.Option(None, "--out", "-o", help="directorio de salida (default: junto a cada spec)"),
    interval: float = typer.Option(1.0, "--interval", "-i", help="sondaje de cambios en segundos"),
) -> None:
    """Vigila specs/ y regenera assets cuando cambian (Ctrl-C para detener)."""
    if not specs_dir.is_dir():
        typer.secho(f"no existe el directorio: {specs_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    files = sorted(specs_dir.glob("*.json"))
    if not files:
        typer.secho(f"no hay specs (*.json) en {specs_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    typer.secho(
        f"[watch] {specs_dir} -> {out or specs_dir} cada {interval}s "
        f"({len(files)} specs) — Ctrl-C para salir",
        fg=typer.colors.CYAN,
    )
    mtimes: dict[Path, float] = {}
    primera = True
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
                if not primera:
                    typer.secho(f"  [cambio] {f.name}", fg=typer.colors.BLUE)
                try:
                    r = _generate(f, out, None, True)
                except SpecError as e:
                    typer.secho(f"  [error] {f.name}: {e}", fg=typer.colors.RED, err=True)
                    continue
                s: Spec = r["spec"]
                if r["skipped"]:
                    typer.secho(f"  [skip]  {s.name} sin cambios (crc {r['crc']:08x})",
                                fg=typer.colors.YELLOW)
                else:
                    typer.secho(
                        f"  [ok]    {s.name} seed={s.seed} frames={s.total_frames} "
                        f"-> {r['out'].resolve()} (crc {r['crc']:08x})",
                        fg=typer.colors.GREEN,
                    )
            primera = False
            time.sleep(interval)
    except KeyboardInterrupt:
        typer.secho("\n[watch] detenido.", fg=typer.colors.CYAN)


@app.callback(invoke_without_command=True)
def _version(version: bool = typer.Option(False, "--version", help="muestra la versión")) -> None:
    if version:
        typer.echo(f"sprout {__version__}")
        raise typer.Exit()


if __name__ == "__main__":
    app()
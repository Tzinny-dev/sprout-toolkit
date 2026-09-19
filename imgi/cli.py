"""CLI `imgi`: generación procedural determinista de assets 2D para Expo.

Uso:
  imgi generate specs/demo.json --out ../demo/assets/procgen
  imgi batch specs/ --out ../demo/assets/procgen
  imgi validate specs/demo.json
"""
from __future__ import annotations

import io
import json
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
from .spec import Spec, SpecError, load_spec

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="imgi — assets 2D procedurales deterministas para Expo + react-native-skia.")


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


@app.callback(invoke_without_command=True)
def _version(version: bool = typer.Option(False, "--version", help="muestra la versión")) -> None:
    if version:
        typer.echo(f"imgi {__version__}")
        raise typer.Exit()


if __name__ == "__main__":
    app()
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from .compiler import compile_file
from .diagrams import (
    DiagramExportProfile,
    DiagramSource,
    DrawioCli,
    default_diagram_registry,
    install_drawio,
)
from .diagrams.drawio_cli import DRAWIO_VERSION
from .errors import DocumentError
from .presets import available_template_presets, describe_template_presets, get_template_preset
from .project import init_project, init_workspace, render_project, validate_project
from .style_import import extract_template, write_style_manifest
from .template import create_template


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docx-harness",
        description="Render Markdown/MyST to deterministic DOCX using project-owned renderers.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    template_parser = subparsers.add_parser(
        "init-template", help="Generate a reusable base DOCX template."
    )
    template_parser.add_argument("output", type=Path)
    template_parser.add_argument("--body-font")
    template_parser.add_argument("--heading-font")
    template_parser.add_argument("--code-font")
    template_parser.add_argument("--accent-color")
    template_parser.add_argument(
        "--preset", choices=available_template_presets(), default="standard"
    )

    subparsers.add_parser("list-presets", help="List maintained template presets.")

    render_parser = subparsers.add_parser("render", help="Render a Markdown/MyST file.")
    render_parser.add_argument("source", type=Path)
    render_parser.add_argument("-o", "--output", type=Path, required=True)
    render_parser.add_argument("--template", type=Path)
    render_parser.add_argument("--diagram-format", choices=("png", "vsdx"), default="png")
    render_parser.add_argument("--auto-install-drawio", action="store_true")

    workspace_parser = subparsers.add_parser(
        "init-workspace", help="Create the repository projects/ workspace."
    )
    workspace_parser.add_argument("repository", type=Path, nargs="?", default=Path("."))

    project_parser = subparsers.add_parser(
        "init-project", help="Initialize one document-category project."
    )
    project_parser.add_argument("name")
    project_parser.add_argument("--workspace", type=Path, default=Path("projects"))
    project_parser.add_argument(
        "--preset", choices=available_template_presets(), default="standard"
    )
    project_parser.add_argument("--from-docx", type=Path)

    project_render_parser = subparsers.add_parser(
        "render-project", help="Render a source with a project's template and extensions."
    )
    project_render_parser.add_argument("project", type=Path)
    project_render_parser.add_argument("source", type=Path, nargs="?")
    project_render_parser.add_argument("-o", "--output", type=Path)
    project_render_parser.add_argument("--diagram-format", choices=("png", "vsdx"), default="png")
    project_render_parser.add_argument("--auto-install-drawio", action="store_true")

    validate_project_parser = subparsers.add_parser(
        "validate-project", help="Run all managed Project preflight checks."
    )
    validate_project_parser.add_argument("project", type=Path)

    install_drawio_parser = subparsers.add_parser(
        "install-drawio", help=f"Install the pinned draw.io {DRAWIO_VERSION} CLI in the user cache."
    )
    install_drawio_parser.add_argument("--cache-dir", type=Path)

    diagram_parser = subparsers.add_parser(
        "convert-diagram", help="Convert Mermaid or native draw.io input through editable mxGraph."
    )
    diagram_parser.add_argument("source", type=Path)
    diagram_parser.add_argument("-o", "--output", type=Path, required=True)
    diagram_parser.add_argument(
        "--source-format", choices=("auto", "mermaid", "drawio"), default="auto"
    )
    diagram_parser.add_argument("--drawio-cli", type=Path)
    diagram_parser.add_argument("--auto-install-drawio", action="store_true")

    inspect_parser = subparsers.add_parser(
        "inspect-docx", help="Write a machine-readable style and table inventory."
    )
    inspect_parser.add_argument("source", type=Path)
    inspect_parser.add_argument("-o", "--output", type=Path, required=True)

    extract_parser = subparsers.add_parser(
        "extract-template", help="Extract a blank template and table prototypes from a DOCX."
    )
    extract_parser.add_argument("source", type=Path)
    extract_parser.add_argument("output", type=Path)
    extract_parser.add_argument("--manifest", type=Path)
    extract_parser.add_argument("--components", type=Path)
    return parser


def _init_template(args: argparse.Namespace):
    base_config = get_template_preset(args.preset).config_factory()
    config = replace(
        base_config,
        body_font=args.body_font or base_config.body_font,
        heading_font=args.heading_font or base_config.heading_font,
        code_font=args.code_font or base_config.code_font,
        accent_color=args.accent_color or base_config.accent_color,
    )
    return create_template(args.output, config, preset=args.preset)


def _list_presets(args: argparse.Namespace):
    del args
    for name, description in describe_template_presets():
        print(f"{name}\t{description}")
    return None


def _render(args: argparse.Namespace):
    return compile_file(
        args.source,
        args.output,
        template=args.template,
        diagram_profile=DiagramExportProfile(
            embed_format=args.diagram_format,
            auto_install_drawio=args.auto_install_drawio,
        ),
    )


def _init_project(args: argparse.Namespace):
    return init_project(
        args.name,
        workspace=args.workspace,
        preset=args.preset,
        from_docx=args.from_docx,
    )


def _render_project(args: argparse.Namespace):
    return render_project(
        args.project,
        args.source,
        output=args.output,
        diagram_profile=DiagramExportProfile(
            embed_format=args.diagram_format,
            auto_install_drawio=args.auto_install_drawio,
        ),
    )


def _convert_diagram(args: argparse.Namespace):
    source_format = args.source_format
    if source_format == "auto":
        source_format = "drawio" if args.source.suffix.lower() == ".drawio" else "mermaid"
    source = DiagramSource(source_format, args.source.read_text(encoding="utf-8"))
    document = default_diagram_registry().convert(source)
    if args.output.suffix.lower() == ".drawio":
        return document.write(args.output)
    output_format = args.output.suffix.lower().lstrip(".")
    if output_format not in {"vsdx", "svg", "png"}:
        raise ValueError("diagram output extension must be .drawio, .vsdx, .svg, or .png")
    intermediate = args.output.with_suffix(".drawio")
    document.write(intermediate)
    return DrawioCli(args.drawio_cli, auto_install=args.auto_install_drawio).export(
        intermediate, args.output, format=output_format
    )


def _extract_template(args: argparse.Namespace):
    return extract_template(
        args.source,
        args.output,
        manifest=args.manifest,
        components=args.components,
    )


def _validate_project(args: argparse.Namespace):
    return validate_project(args.project)


def _dispatch(args: argparse.Namespace):
    handlers = {
        "init-template": _init_template,
        "list-presets": _list_presets,
        "render": _render,
        "init-workspace": lambda value: init_workspace(value.repository),
        "init-project": _init_project,
        "render-project": _render_project,
        "validate-project": _validate_project,
        "install-drawio": lambda value: install_drawio(cache_dir=value.cache_dir),
        "convert-diagram": _convert_diagram,
        "inspect-docx": lambda value: write_style_manifest(value.source, value.output),
        "extract-template": _extract_template,
    }
    return handlers[args.command](args)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = _dispatch(args)
    except (DocumentError, OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    if output is not None:
        print(output)
    return 0

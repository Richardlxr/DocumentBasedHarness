"""Deck diagrams: visual.diagram (mermaid) → PNG via the vendored compiler.

Reuses docx-harness's deterministic chain — Mermaid source → native mxGraph
nodes with measured, collision-checked layout → draw.io CLI export. The PNG is
cached under ``build/diagrams/`` keyed by a content hash: identical diagram
source is compiled once per run workspace.

The mermaid → DrawioDocument conversion itself is pure Python (no CLI), which
``comh validate`` exploits to dry-run diagram syntax before any render.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from docx_harness import DiagramArtifactBuilder, DiagramSource
from docx_harness.errors import DocumentError, SourceLocation


def dry_convert(mermaid: str) -> str | None:
    """Convert mermaid to a DrawioDocument without touching the CLI.

    Returns None on success; on failure returns a human-readable error
    (used by validators so bad diagram syntax fails at `comh validate`,
    not at render time).
    """
    from docx_harness.diagrams import default_diagram_registry

    try:
        default_diagram_registry().convert(
            DiagramSource("mermaid", mermaid, SourceLocation("deck_plan"))
        )
    except DocumentError as error:
        return str(error)
    return None


def diagram_png(mermaid: str, run_root: Path) -> Path:
    """Compile mermaid to a cached PNG under build/diagrams/."""
    digest = hashlib.sha256(mermaid.encode("utf-8")).hexdigest()[:10]
    cache_dir = run_root / "build" / "diagrams"
    png = cache_dir / f"deck-{digest}.png"
    if png.is_file():
        return png
    builder = DiagramArtifactBuilder()
    artifact = builder.build(
        DiagramSource("mermaid", mermaid, SourceLocation("deck_plan")),
        cache_dir,
        stem=f"deck-{digest}",
    )
    return artifact.require("png")

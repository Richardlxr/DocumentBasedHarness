"""Report renderer: documents/report.md → build/report.docx.

Markdown is the canonical report deliverable; DOCX is the secondary, compiled
output. Compilation goes through the vendored docx_harness public API, which
fails loudly on unsupported dialect instead of degrading — those failures are
free deterministic QA for the authoring stage.
"""

from __future__ import annotations

from pathlib import Path

from docx_harness import compile_file


def render_report(source: Path, template: Path, output: Path) -> Path:
    if not source.is_file():
        raise FileNotFoundError(f"report source missing: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    return compile_file(str(source), str(output), template=str(template))

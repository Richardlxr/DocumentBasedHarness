"""Diagram chain tests: dry conversion (no CLI), validation wiring, and a
render smoke test that runs only when a draw.io CLI is configured."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from comh.render.diagrams import diagram_png, dry_convert
from comh.validate import validate_visuals

VALID = "flowchart LR\n  gen[负载生成器] -->|线上流量模型| n1[节点 1]\n"
UNSUPPORTED_SUBGRAPH = "flowchart TB\n  subgraph s[池]\n    a --> b\n  end\n"
UNSUPPORTED_DOTTED_LABEL = "flowchart LR\n  a --> b\n  b -.文本.-> c[节点]\n"


def test_dry_convert_valid_mermaid_passes() -> None:
    assert dry_convert(VALID) is None


def test_dry_convert_catches_unsupported_syntax() -> None:
    error = dry_convert(UNSUPPORTED_SUBGRAPH)
    assert error and "unsupported" in error
    error = dry_convert(UNSUPPORTED_DOTTED_LABEL)
    assert error and "unsupported" in error


def _deck_page(**visual) -> dict:
    return {
        "id": "P01",
        "page_role": "content",
        "title": "x",
        "visual": visual,
    }


def test_visual_validation_dry_runs_diagrams() -> None:
    artifacts = {
        "evidence": {"items": []},
        "deck_plan": {
            "deck": {
                "title": "t",
                "pages": [_deck_page(diagram={"mermaid": UNSUPPORTED_SUBGRAPH})],
            }
        },
    }
    findings = validate_visuals(artifacts)
    assert any(f.check == "diagram" and f.severity == "error" for f in findings)


def test_visual_validation_diagram_evidence_and_misplaced_keys() -> None:
    artifacts = {
        "evidence": {"items": []},
        "deck_plan": {
            "deck": {
                "title": "t",
                "pages": [
                    {
                        "id": "P01",
                        "page_role": "content",
                        "title": "x",
                        "chart": {"series": []},  # misplaced: page level, not visual
                        "visual": {"diagram": {"mermaid": VALID, "evidence": "E999"}},
                    }
                ],
            }
        },
    }
    findings = validate_visuals(artifacts)
    details = " | ".join(f.detail for f in findings)
    assert "diagram references missing evidence 'E999'" in details
    assert "'chart' at page level" in details


@pytest.mark.skipif(
    not (os.environ.get("DRAWIO_CLI") or shutil.which("drawio")),
    reason="draw.io CLI not configured (set DRAWIO_CLI)",
)
def test_diagram_png_compiles_and_caches(tmp_path: Path) -> None:
    png = diagram_png(VALID, tmp_path)
    assert png.is_file()
    # second call hits the content-hash cache
    assert diagram_png(VALID, tmp_path) == png

"""Evidence-pack slicing tests (the repair loop's forensic tool)."""

from __future__ import annotations

from pathlib import Path

from comh.evidence_pack import build_pack
from comh.scaffold import init_run

EVIDENCE = """\
version: 1
items:
  - id: E001
    kind: datum
    content: "基线 220ms"
    source: {source: SRC01, locator: row=1}
  - id: E002
    kind: figure
    content: 对比图
    asset: assets/fig.png
    source: {source: SRC01, locator: row=2}
"""

NARRATIVE = """\
version: 1
claims:
  - id: C01
    statement: "P99 从 220ms 降至 180ms"
    evidence: [E001]
    status: supported
story:
  - {id: S01, purpose: demonstrate_effect, message: m, claims: [C01]}
"""

DECK = """\
version: 1
deck:
  title: t
  pages:
    - id: P01
      page_role: content
      beat: S01
      title: T
      visual:
        asset_refs:
          - {ref: assets/fig.png, caption: 图注, evidence: E002}
"""


def _setup(tmp_path: Path) -> Path:
    root = init_run(tmp_path / "run", "pack-run")
    (root / "evidence" / "evidence.yaml").write_text(EVIDENCE, encoding="utf-8")
    (root / "narrative" / "narrative.yaml").write_text(NARRATIVE, encoding="utf-8")
    (root / "projection" / "deck_plan.yaml").write_text(DECK, encoding="utf-8")
    return root


def test_pack_includes_claim_evidence_and_figure_evidence(tmp_path: Path):
    pack = build_pack(_setup(tmp_path), "deck", "P01")
    evidence_ids = [item["id"] for item in pack["evidence"]]
    # E001 arrives via the claim chain; E002 only via the figure's linkage.
    assert evidence_ids == ["E001", "E002"]
    assert pack["beats"][0]["id"] == "S01"
    assert pack["claims"][0]["id"] == "C01"


def test_pack_unknown_node_raises(tmp_path: Path):
    import pytest

    root = _setup(tmp_path)
    with pytest.raises(KeyError):
        build_pack(root, "deck", "P99")

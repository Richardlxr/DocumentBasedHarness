"""Manifest state-machine tests: save, gates, transitive staleness."""

from __future__ import annotations

import pytest

from comh.manifest import Manifest, RunError
from comh.scaffold import init_run


@pytest.fixture()
def run_root(tmp_path):
    return init_run(tmp_path / "run", "test-run")


def _write(root, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


MIN_EVIDENCE = "version: 1\nitems: []\n"
MIN_BRIEF = (
    "version: 1\n"
    "language: zh-CN\n"
    "version: 1\n"
    "audience: {description: x}\n"
    "objective: y\n"
    "media: [{medium: pptx, surface: presentation}]\n"
    "takeaways: [z]\n"
)
MIN_NARRATIVE = (
    "version: 1\nclaims: []\nstory:\n  - {id: S01, purpose: p, message: m}\n"
)


def test_guard_blocks_narrative_before_gate(run_root):
    manifest = Manifest.load(run_root)
    _write(run_root, "evidence/evidence.yaml", MIN_EVIDENCE)
    _write(run_root, "brief/brief.yaml", MIN_BRIEF)
    manifest.mark_saved("evidence")
    manifest.mark_saved("brief")
    _write(run_root, "narrative/narrative.yaml", MIN_NARRATIVE)
    with pytest.raises(RunError, match="gate 'brief' is not confirmed"):
        manifest.require_gate("brief")


def _confirmed_through_narrative(run_root) -> Manifest:
    manifest = Manifest.load(run_root)
    _write(run_root, "evidence/evidence.yaml", MIN_EVIDENCE)
    _write(run_root, "brief/brief.yaml", MIN_BRIEF)
    _write(run_root, "narrative/narrative.yaml", MIN_NARRATIVE)
    manifest.mark_saved("evidence")
    manifest.mark_saved("brief")
    manifest.confirm_gate("brief")
    manifest.mark_saved("narrative")
    manifest.confirm_gate("narrative")
    return manifest


def test_transitive_staleness_from_source_change(run_root):
    manifest = _confirmed_through_narrative(run_root)
    assert manifest.artifact_state("narrative").state == "confirmed"
    # change a source file -> evidence stale -> everything downstream stale
    (run_root / "sources" / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    assert manifest.artifact_state("evidence").state == "stale"
    assert manifest.artifact_state("brief").state == "stale"
    assert manifest.artifact_state("narrative").state == "stale"
    with pytest.raises(RunError, match="stale"):
        manifest.require_fresh("narrative")


def test_identical_resave_keeps_gate_changed_content_resets(run_root):
    manifest = _confirmed_through_narrative(run_root)
    (run_root / "sources" / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    manifest.mark_saved("evidence")
    manifest.mark_saved("brief")  # identical bytes -> gate must survive
    assert manifest.gate_valid("brief")
    manifest.mark_saved("narrative")  # identical bytes -> gate survives
    assert manifest.gate_valid("narrative")
    # now actually edit the narrative -> gate resets
    _write(run_root, "narrative/narrative.yaml", MIN_NARRATIVE + "# edited\n")
    manifest.mark_saved("narrative")
    assert not manifest.gate_valid("narrative")


def test_gate_invalidated_by_post_confirmation_edit(run_root):
    manifest = _confirmed_through_narrative(run_root)
    _write(run_root, "brief/brief.yaml", MIN_BRIEF + "# touched\n")
    with pytest.raises(RunError, match="invalidated"):
        manifest.require_gate("brief")

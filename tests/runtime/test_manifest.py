"""Manifest state-machine tests: save, gates, transitive staleness."""

from __future__ import annotations

import pytest
import yaml
from workflow_helpers import aligned, approve, prepare

from comh.manifest import Manifest, RunError
from comh.scaffold import init_run


@pytest.fixture()
def run_root(tmp_path):
    return init_run(tmp_path / "run", "test-run")


def _write(root, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if rel == "brief/brief.yaml":
        text = yaml.safe_dump(aligned(yaml.safe_load(text)), allow_unicode=True) + (
            "# touched\n" if "#" in text else ""
        )
        prepare(root)
    path.write_text(text, encoding="utf-8")


MIN_EVIDENCE = "version: 1\nitems: []\n"
MIN_BRIEF = (
    "version: 1\n"
    "language: zh-CN\n"
    "audience: {description: x}\n"
    "objective: y\n"
    "media: [{medium: pptx, surface: presentation}]\n"
    "takeaways: [z]\n"
)
MIN_NARRATIVE = "version: 1\nclaims: []\nstory:\n  - {id: S01, purpose: p, message: m}\n"


def test_guard_blocks_narrative_before_gate(run_root):
    manifest = Manifest.load(run_root)
    _write(run_root, "evidence/evidence.yaml", MIN_EVIDENCE)
    _write(run_root, "brief/brief.yaml", MIN_BRIEF)
    manifest = Manifest.load(run_root)
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
    manifest = Manifest.load(run_root)
    manifest.mark_saved("evidence")
    manifest.mark_saved("brief")
    assert approve(run_root, "brief") == 0
    manifest = Manifest.load(run_root)
    manifest.mark_saved("narrative")
    assert approve(run_root, "narrative") == 0
    manifest = Manifest.load(run_root)
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


def test_identical_resave_preserves_gate_only_with_unchanged_basis(run_root):
    manifest = _confirmed_through_narrative(run_root)
    manifest.mark_saved("brief")
    manifest.mark_saved("narrative")
    assert manifest.gate_valid("brief")
    assert manifest.gate_valid("narrative")
    (run_root / "sources" / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    manifest = Manifest.load(run_root)
    manifest.mark_saved("evidence")
    manifest.mark_saved("brief")  # same bytes, but a new source basis
    assert not manifest.gate_valid("brief")  # changed evidence basis requires new acceptance
    prepare(run_root)
    assert approve(run_root, "brief") == 0
    manifest = Manifest.load(run_root)
    manifest.mark_saved("narrative")
    assert not manifest.gate_valid("narrative")
    assert approve(run_root, "narrative") == 0
    manifest = Manifest.load(run_root)
    # now actually edit the narrative -> gate resets
    _write(run_root, "narrative/narrative.yaml", MIN_NARRATIVE + "# edited\n")
    manifest.mark_saved("narrative")
    assert not manifest.gate_valid("narrative")


def test_gate_invalidated_by_post_confirmation_edit(run_root):
    manifest = _confirmed_through_narrative(run_root)
    _write(run_root, "brief/brief.yaml", MIN_BRIEF + "# touched\n")
    with pytest.raises(RunError, match="invalidated"):
        manifest.require_gate("brief")


def test_validate_output_never_prints_an_empty_fix_hint(run_root, capsys):
    """Findings default owning_artifact to "", meaning "this artifact owns it".
    The CLI must compare the normalized value or every such finding prints a
    dangling `→ fix:`."""
    from comh.artifacts import Finding
    from comh.cli import main

    assert Finding("evidence", "c", "warn", "fail", "d").as_dict()["owning_artifact"] == "evidence"
    # A derived item with no formula yields a finding built without an explicit
    # owner — exactly the shape that used to print a dangling hint.
    _write(
        run_root,
        "evidence/evidence.yaml",
        "version: 1\nitems:\n"
        "  - {id: E001, kind: datum, content: a, value: {number: 1, unit: ms},\n"
        "     source: {source: derived, locator: 'derived:(E002)'}}\n"
        "  - {id: E002, kind: datum, content: b, value: {number: 1, unit: ms},\n"
        "     source: {source: derived, locator: 'derived:()'}}\n",
    )
    _write(run_root, "brief/brief.yaml", MIN_BRIEF)
    main(["validate", "evidence", "--run", str(run_root)])
    out = capsys.readouterr().out
    assert "derived-calculation" in out  # the test would be vacuous otherwise
    assert "→ fix: \n" not in out

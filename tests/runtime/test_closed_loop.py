"""Closed-loop hardening tests.

Covers the audit fixes: validate hard-chained into save/confirm/render,
evidence→source validation, evidence-pack placeholders, deliver acceptance,
CSS color variables, and the theme-from-pptx CLI wiring.
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation

from comh.cli import build_parser, cmd_theme_from_pptx, main
from comh.scaffold import init_run

MIN_EVIDENCE = """version: 1
sources:
  - {id: SRC01, path: sources/a.csv, kind: csv}
items:
  - id: E001
    kind: datum
    content: "基线 220ms"
    value: {number: 220, unit: ms}
    source: {source: SRC01, locator: "row=1"}
"""

MIN_BRIEF = (
    "version: 1\n"
    "language: zh-CN\n"
    "audience: {description: x}\n"
    "objective: y\n"
    "media: [{medium: pptx, surface: presentation}]\n"
    "takeaways: [z]\n"
)

GOOD_NARRATIVE = (
    "version: 1\n"
    "claims:\n"
    "  - {id: C01, statement: P99 降至 220ms, evidence: [E001], status: supported}\n"
    "story:\n"
    "  - {id: S01, purpose: demonstrate_effect, message: m, claims: [C01]}\n"
)

DANGLING_NARRATIVE = (
    "version: 1\n"
    "claims:\n"
    "  - {id: C01, statement: 见数据, evidence: [E999], status: supported}\n"
    "story:\n"
    "  - {id: S01, purpose: demonstrate_effect, message: m, claims: [C01]}\n"
)

MIN_DECK_PLAN = """version: 1
deck:
  title: t
  pages:
    - {id: P01, page_role: content, beat: S01, title: "P99 220ms", support_points: ["点一"]}
"""


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _pipeline_through_narrative(root: Path) -> None:
    (root / "sources" / "a.csv").write_text("v\n220\n", encoding="utf-8")
    _write(root, "evidence/evidence.yaml", MIN_EVIDENCE)
    _write(root, "brief/brief.yaml", MIN_BRIEF)
    _write(root, "narrative/narrative.yaml", GOOD_NARRATIVE)
    assert main(["save", "evidence", "--run", str(root)]) == 0
    assert main(["save", "brief", "--run", str(root)]) == 0
    assert main(["confirm", "brief", "--run", str(root)]) == 0
    assert main(["save", "narrative", "--run", str(root)]) == 0
    assert main(["confirm", "narrative", "--run", str(root)]) == 0


def test_theme_from_pptx_is_registered_and_runs(tmp_path: Path, capsys):
    run = init_run(tmp_path / "run", "t")
    template = tmp_path / "template.pptx"
    Presentation().save(str(template))

    args = build_parser().parse_args(
        ["theme-from-pptx", str(template), "--name", "brand", "--run", str(run)]
    )
    assert args.func is cmd_theme_from_pptx
    assert main(["theme-from-pptx", str(template), "--name", "brand", "--run", str(run)]) == 0
    assert (run / "themes" / "brand" / "theme.yaml").is_file()


def test_save_blocks_on_dangling_evidence_ref(tmp_path: Path):
    run = init_run(tmp_path / "run", "t")
    (run / "sources" / "a.csv").write_text("v\n", encoding="utf-8")
    _write(run, "evidence/evidence.yaml", MIN_EVIDENCE)
    _write(run, "brief/brief.yaml", MIN_BRIEF)
    assert main(["save", "evidence", "--run", str(run)]) == 0
    assert main(["save", "brief", "--run", str(run)]) == 0
    assert main(["confirm", "brief", "--run", str(run)]) == 0
    _write(run, "narrative/narrative.yaml", DANGLING_NARRATIVE)
    blocked = main(["save", "narrative", "--run", str(run)])
    assert blocked == 2, "ref-integrity error must block save"
    _write(run, "narrative/narrative.yaml", GOOD_NARRATIVE)
    assert main(["save", "narrative", "--run", str(run)]) == 0


def test_confirm_requires_saved_fresh_state(tmp_path: Path):
    run = init_run(tmp_path / "run", "t")
    (run / "sources" / "a.csv").write_text("v\n", encoding="utf-8")
    _write(run, "evidence/evidence.yaml", MIN_EVIDENCE)
    _write(run, "brief/brief.yaml", MIN_BRIEF)
    assert main(["save", "evidence", "--run", str(run)]) == 0
    assert main(["save", "brief", "--run", str(run)]) == 0
    # hand-edit after save: not fresh → confirm refused (schema/validate never ran)
    _write(run, "brief/brief.yaml", MIN_BRIEF + "voice: {style: plain}\n")
    assert main(["confirm", "brief", "--run", str(run)]) == 2
    assert main(["save", "brief", "--run", str(run)]) == 0
    assert main(["confirm", "brief", "--run", str(run)]) == 0


def test_render_blocked_by_validation_errors_and_deliver_flow(tmp_path: Path, capsys):
    run = init_run(tmp_path / "run", "t")
    _pipeline_through_narrative(run)
    _write(run, "projection/deck_plan.yaml", MIN_DECK_PLAN)
    assert main(["save", "deck_plan", "--run", str(run)]) == 0
    assert main(["render", "deck", "--run", str(run)]) == 0

    # deliver before acceptance: records and pins output hashes
    assert main(["deliver", "--run", str(run), "--note", "user read-through ok"]) == 0
    status = capsys.readouterr().out
    assert main(["status", "--run", str(run)]) == 0
    status = capsys.readouterr().out
    assert "accepted at" in status and "delivery" in status

    # re-render changes the output hash → acceptance invalidated until re-accepted
    output = run / "build" / "deck.pptx"
    output.write_bytes(output.read_bytes() + b"\0")
    assert main(["status", "--run", str(run)]) == 0
    assert "invalidated" in capsys.readouterr().out
    assert main(["deliver", "--run", str(run)]) == 0

    # a deck_plan with a dangling beat ref cannot be saved, let alone rendered
    _write(run, "projection/deck_plan.yaml", MIN_DECK_PLAN.replace("beat: S01", "beat: S99"))
    assert main(["save", "deck_plan", "--run", str(run)]) == 2


def test_deliver_without_outputs_is_refused(tmp_path: Path):
    run = init_run(tmp_path / "run", "t")
    _pipeline_through_narrative(run)
    assert main(["deliver", "--run", str(run)]) == 2


def test_validate_sources_catches_broken_chain(tmp_path: Path):
    from comh.validate import validate_sources

    artifacts = {
        "evidence": {
            "sources": [
                {"id": "SRC01", "path": "sources/exists.csv"},
                {"id": "SRC02", "path": "sources/gone.csv"},
            ],
            "items": [
                {
                    "id": "E001",
                    "kind": "datum",
                    "content": "a",
                    "source": {"source": "SRC01", "locator": "r1"},
                },
                {
                    "id": "E002",
                    "kind": "datum",
                    "content": "b",
                    "source": {"source": "SRC02", "locator": "r1"},
                },
                {
                    "id": "E003",
                    "kind": "datum",
                    "content": "c",
                    "source": {"source": "SRC09", "locator": "r1"},
                },
                {
                    "id": "E004",
                    "kind": "datum",
                    "content": "d",
                    "source": {"source": "derived", "locator": "derived:(E001,E888)"},
                },
            ],
        }
    }
    (tmp_path / "sources").mkdir(exist_ok=True)
    (tmp_path / "sources" / "exists.csv").write_text("x\n", encoding="utf-8")
    findings = validate_sources(artifacts, tmp_path)
    details = " | ".join(f.detail for f in findings)
    assert "E003" in details and "SRC09" in details, "unknown SRC id is an error"
    assert "E002" in details and "gone.csv" in details, "missing registry path is an error"
    assert "E004" in details and "E888" in details, "derived operands must exist"
    assert not any("E001" in f.detail and f.severity == "error" for f in findings)

    no_registry = {"evidence": {"items": artifacts["evidence"]["items"][:1]}}
    warns = validate_sources(no_registry, tmp_path)
    assert any(f.check == "source-registry" and f.severity == "warn" for f in warns)


def test_coverage_respects_dropped_projection_status():
    from comh.validate import validate_coverage

    artifacts = {
        "narrative": {
            "story": [
                {"id": "S01", "purpose": "p", "message": "m", "claims": []},
                {
                    "id": "S02",
                    "purpose": "p",
                    "message": "m",
                    "claims": [],
                    "projection": {"status": "dropped", "note": "附录材料"},
                },
            ]
        },
        "deck_plan": {"deck": {"pages": [{"id": "P01", "beat": "S01", "title": "t"}]}},
        "report_plan": {"sections": []},
    }
    findings = validate_coverage(artifacts)
    dropped = [f for f in findings if "S02" in f.detail]
    assert dropped and dropped[0].severity == "info" and dropped[0].owning_artifact == "narrative"
    assert not any(f.severity == "warn" for f in findings)


def test_unmachineable_hard_constraint_warns():
    from comh.validate import validate_hard_constraints

    artifacts = {"brief": {"constraints": {"hard": ["语气要自信", "必须包含:局限性"]}}}
    findings = validate_hard_constraints(artifacts, None)
    unmappable = [f for f in findings if "语气要自信" in f.detail]
    assert unmappable and unmappable[0].severity == "warn"
    assert not any("必须包含" in f.detail and "no machine check" in f.detail for f in findings)


def test_evidence_pack_marks_missing_source(tmp_path: Path):
    from comh.evidence_pack import build_pack

    run = init_run(tmp_path / "run", "t")
    broken_ref = MIN_EVIDENCE.replace("{source: SRC01, locator", "{source: SRC05, locator")
    _write(run, "evidence/evidence.yaml", broken_ref)
    _write(run, "narrative/narrative.yaml", GOOD_NARRATIVE)
    _write(run, "projection/deck_plan.yaml", MIN_DECK_PLAN)
    pack = build_pack(run, "deck", "P01")
    broken = [s for s in pack["sources"] if "error" in s]
    assert broken and broken[0]["id"] == "SRC05"


def test_broken_theme_file_gets_specific_message(tmp_path: Path):
    from comh.render.theme import select_theme

    run = tmp_path / "run"
    theme_dir = run / "themes" / "brand"
    theme_dir.mkdir(parents=True)
    (theme_dir / "theme.yaml").write_text("colors: {background: 'nope'}\n", encoding="utf-8")
    choice = select_theme({"template": "brand"}, run_root=run)
    assert choice.fallback_reason and "invalid" in choice.fallback_reason
    unknown = select_theme({"template": "brand-new"}, run_root=run)
    assert "unknown template" in unknown.fallback_reason


def test_html_css_colors_carry_hash_prefix(tmp_path: Path):
    from comh.render.html_deck import render_html_deck

    plan = {
        "version": 1,
        "deck": {
            "title": "t",
            "pages": [
                {"id": "P01", "page_role": "content", "title": "标题", "support_points": ["点"]}
            ],
        },
    }
    render_html_deck(plan, tmp_path, tmp_path / "deck.html", language="zh-CN")
    css = (tmp_path / "deck.html").read_text(encoding="utf-8")
    assert "--bg:#" in css and "--accent:#" in css and "--text:#" in css, (
        "bare hex values are invalid CSS colors and strip the whole theme"
    )

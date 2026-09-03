"""Regression scenarios for the workflow audit, including negative delivery paths."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from workflow_helpers import aligned, approve, prepare, simulated_reader

from comh.artifacts import load_artifact, validate_schema
from comh.cli import main
from comh.evidence_pack import build_pack
from comh.manifest import Manifest
from comh.scaffold import init_run
from comh.validate import run_all, validate_coverage, validate_numbers, validate_sources

EVIDENCE = {
    "version": 1,
    "sources": [{"id": "SRC01", "path": "sources/data.csv"}],
    "items": [
        {
            "id": "E001",
            "kind": "datum",
            "content": "基线 220 ms",
            "value": {"number": 220, "unit": "ms"},
            "source": {"source": "SRC01", "locator": "row=2"},
        },
        {
            "id": "E002",
            "kind": "datum",
            "content": "优化后 180 ms",
            "value": {"number": 180, "unit": "ms"},
            "source": {"source": "SRC01", "locator": "row=3"},
        },
    ],
}
BRIEF = {
    "version": 1,
    "language": "zh-CN",
    "audience": {"description": "评审者"},
    "objective": "评估延迟",
    "media": [{"medium": "pptx", "surface": "presentation"}],
    "takeaways": ["了解基线延迟"],
}
NARRATIVE = {
    "version": 1,
    "claims": [
        {"id": "C01", "statement": "基线为 220 ms", "evidence": ["E001"], "status": "supported"}
    ],
    "story": [
        {
            "id": "S01",
            "purpose": "demonstrate_effect",
            "message": "基线为 220 ms",
            "claims": ["C01"],
        }
    ],
}
DECK = {
    "version": 1,
    "deck": {
        "title": "实验结果",
        "pages": [
            {
                "id": "P01",
                "page_role": "content",
                "beat": "S01",
                "title": "基线为 220 ms",
                "support_points": ["基线实验"],
            }
        ],
    },
}
REPORT_PLAN = {
    "version": 1,
    "sections": [
        {
            "id": "R01",
            "heading": "实验结果",
            "beats": ["S01"],
            "claims": ["C01"],
            "evidence": ["E001"],
            "must_include": ["测量边界"],
        }
    ],
}
REPORT = "# 实验报告\n\n## 一、实验结果\n\n基线为 220 ms。[E001]\n\n测量边界：受控负载。\n"


def write(root, rel, data):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        data
        if isinstance(data, str)
        else yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def cli(root, *args):
    return main([*args, "--run", str(root)])


def pipeline(tmp_path, brief=None):
    root = init_run(tmp_path / "run")
    write(root, "sources/data.csv", "latency_ms\n220\n180\n")
    prepare(root)
    for key, rel, data in (
        ("evidence", "evidence/evidence.yaml", EVIDENCE),
        ("brief", "brief/brief.yaml", aligned(brief or BRIEF)),
        ("narrative", "narrative/narrative.yaml", NARRATIVE),
    ):
        write(root, rel, data)
        assert cli(root, "save", key) == 0
        if key in {"brief", "narrative"}:
            assert approve(root, key) == 0
    return root


def deck_run(tmp_path, brief=None):
    root = pipeline(tmp_path, brief)
    write(root, "projection/deck_plan.yaml", DECK)
    assert cli(root, "save", "deck_plan") == 0
    assert approve(root, "deck_outline") == 0
    assert cli(root, "render", "deck") == 0
    return root


def review(root, findings=None, manual=None):
    path = write(
        root,
        ".workspace/review-input.yaml",
        {
            "completed_checks": ["narrative", "audience", "reader", "style"],
            "reader_test": simulated_reader(root),
            "findings": findings or [],
            "manual_constraints": manual or [],
        },
    )
    assert cli(root, "review", str(path)) == 0


def test_changed_plan_cannot_reaccept_old_output(tmp_path):
    root = deck_run(tmp_path)
    review(root)
    assert approve(root, "delivery") == 0
    assert cli(root, "deliver") == 0
    changed = deepcopy(DECK)
    changed["deck"]["pages"][0]["title"] = "修改后的结论"
    write(root, "projection/deck_plan.yaml", changed)
    assert cli(root, "save", "deck_plan") == 0
    assert Manifest.load(root).delivery_state()[0] == "invalidated"
    assert cli(root, "deliver") == 2
    assert approve(root, "deck_outline") == 0
    assert cli(root, "render", "deck") == 0
    assert cli(root, "deliver") == 2  # rendering cannot refresh a model review
    review(root)
    assert approve(root, "delivery") == 0
    assert cli(root, "deliver") == 0


@pytest.mark.parametrize(
    "rel",
    [
        "sources/data.csv",
        "assets/new.txt",
        "themes/brand/theme.yaml",
        "templates/base.docx",
        "build/deck.pptx",
        "qa/render-deck.yaml",
    ],
)
def test_changed_dependencies_and_output_invalidate_delivery(tmp_path, rel):
    root = deck_run(tmp_path)
    review(root)
    assert approve(root, "delivery") == 0
    assert cli(root, "deliver") == 0
    write(root, rel, "changed")
    assert Manifest.load(root).delivery_state()[0] == "invalidated"
    assert cli(root, "deliver") == 2


def test_source_drift_invalidates_gates_and_blocks_downstream_save(tmp_path):
    root = deck_run(tmp_path)
    write(root, "sources/data.csv", "latency_ms\n999\n")
    manifest = Manifest.load(root)
    assert manifest.artifact_state("brief").state == "stale"
    assert not manifest.gate_valid("brief")
    assert not manifest.gate_valid("narrative")
    assert cli(root, "save", "deck_plan") == 2


def test_qa_errors_survive_validation_and_block_delivery(tmp_path):
    root = deck_run(tmp_path)
    assert cli(root, "deliver") == 2  # review is mandatory
    finding = {
        "artifact": "narrative",
        "check": "model:logic",
        "severity": "error",
        "detail": "结论缺乏依据",
        "owning_artifact": "narrative",
    }
    review(root, [finding])
    assert cli(root, "validate", "all") == 1
    assert cli(root, "validate", "all") == 1
    assert yaml.safe_load((root / "qa/model-findings.yaml").read_text())["findings"] == [finding]
    assert cli(root, "deliver") == 2
    assert cli(root, "save", "evidence") == 0  # a finding cannot deadlock its repair
    review(root)
    assert approve(root, "delivery") == 0
    assert cli(root, "deliver") == 0


def test_legacy_model_findings_are_preserved_without_fabricating_review(tmp_path):
    root = deck_run(tmp_path)
    finding = {
        "artifact": "deck_plan",
        "check": "model:title",
        "severity": "error",
        "detail": "title mismatch",
    }
    write(root, "qa/findings.yaml", {"findings": [finding]})
    assert cli(root, "validate", "all") == 1
    stored = yaml.safe_load((root / "qa/model-findings.yaml").read_text())
    assert stored["findings"] == [finding] and stored["inputs"] is None
    assert cli(root, "deliver") == 2


def test_failed_render_cannot_deliver_previous_success(tmp_path, monkeypatch):
    from comh.artifacts import Finding

    root = deck_run(tmp_path)
    review(root)
    assert approve(root, "delivery") == 0
    assert cli(root, "deliver") == 0

    def fail(plan, run_root, output, **kwargs):
        output.write_bytes(b"bad output")
        return SimpleNamespace(
            theme="test",
            transition=None,
            findings=[Finding("deck_plan", "layout", "error", "fail", "overlap")],
        )

    monkeypatch.setattr("comh.cli.render_deck", fail)
    assert cli(root, "render", "deck") == 1
    assert cli(root, "deliver") == 2
    assert cli(root, "validate", "all") == 1


def test_byte_identical_rerender_invalidates_review(tmp_path, monkeypatch):
    root = deck_run(tmp_path)
    review(root)
    assert approve(root, "delivery") == 0
    assert cli(root, "deliver") == 0
    monkeypatch.setattr(
        "comh.cli.render_deck",
        lambda *a, **k: SimpleNamespace(theme="test", transition=None, findings=[]),
    )
    assert approve(root, "deck_outline") == 0
    assert cli(root, "render", "deck") == 0
    assert Manifest.load(root).delivery_state()[0] == "invalidated"
    assert cli(root, "deliver") == 2


def test_gate1_allows_pending_constraint_but_plan_must_satisfy_it(tmp_path):
    brief = deepcopy(BRIEF)
    brief["constraints"] = {"hard": ["必须包含:局限性"]}
    root = pipeline(tmp_path, brief)
    write(root, "projection/deck_plan.yaml", DECK)
    assert cli(root, "save", "deck_plan") == 2
    changed = deepcopy(DECK)
    changed["deck"]["pages"][0]["support_points"] = ["局限性：固定负载"]
    write(root, "projection/deck_plan.yaml", changed)
    assert cli(root, "save", "deck_plan") == 0


def test_invalid_sibling_does_not_block_upstream_or_selected_medium(tmp_path):
    root = deck_run(tmp_path)
    write(root, "projection/report_plan.yaml", {"sections": [{"heading": "missing id"}]})
    assert cli(root, "save", "evidence") == 0
    assert cli(root, "validate", "deck_plan") == 0
    assert cli(root, "validate", "all") == 0


def test_markdown_only_delivery_pins_canonical_source(tmp_path):
    brief = deepcopy(BRIEF)
    brief["media"] = [{"medium": "markdown", "surface": "report"}]
    root = pipeline(tmp_path, brief)
    write(root, "projection/report_plan.yaml", REPORT_PLAN)
    assert cli(root, "save", "report_plan") == 0
    assert approve(root, "report_outline") == 0
    write(root, "documents/report.md", REPORT)
    assert cli(root, "save", "report_md") == 0
    assert cli(root, "validate", "all") == 0
    review(root)
    assert approve(root, "delivery") == 0
    assert cli(root, "deliver") == 0
    record = Manifest.load(root).delivery_state()[1]
    assert list(record["outputs"]) == ["documents/report.md"]
    write(root, "documents/report.md", REPORT + "新增内容。\n")
    assert Manifest.load(root).delivery_state()[0] == "invalidated"


def test_every_requested_medium_is_required(tmp_path):
    brief = deepcopy(BRIEF)
    brief["media"].append({"medium": "markdown", "surface": "report"})
    root = deck_run(tmp_path, brief)
    assert cli(root, "deliver") == 2


@pytest.mark.parametrize(
    "text",
    [
        REPORT.replace("[E001]", "[E999]"),
        REPORT.replace("测量边界", "其他内容"),
        REPORT.replace("实验结果", "不同章节"),
        REPORT + "\n## 实验结果\n重复章节。",
    ],
)
def test_report_contract_blocks_missing_content_or_bad_citations(tmp_path, text):
    root = pipeline(tmp_path)
    write(root, "projection/report_plan.yaml", REPORT_PLAN)
    assert cli(root, "save", "report_plan") == 0
    assert approve(root, "report_outline") == 0
    write(root, "documents/report.md", text)
    assert cli(root, "save", "report_md") == 2


@pytest.mark.parametrize("statement", ["基线为 180 ms", "基线为 220 s"])
def test_claim_numbers_and_units_match_cited_evidence(statement):
    narrative = deepcopy(NARRATIVE)
    narrative["claims"][0]["statement"] = statement
    findings = validate_numbers({"evidence": EVIDENCE, "narrative": narrative}, None)
    assert any(f.severity == "error" for f in findings)


@pytest.mark.parametrize(
    "name,data,collection",
    [
        ("evidence", EVIDENCE, "items"),
        ("evidence", EVIDENCE, "sources"),
        ("narrative", NARRATIVE, "claims"),
        ("narrative", NARRATIVE, "story"),
        ("report_plan", REPORT_PLAN, "sections"),
    ],
)
def test_duplicate_ids_are_rejected(name, data, collection):
    duplicate = deepcopy(data)
    duplicate[collection].append(deepcopy(duplicate[collection][0]))
    assert any("duplicate ID" in e for e in validate_schema(name, duplicate))


def test_malformed_artifact_yields_schema_errors_not_exception(tmp_path):
    root = pipeline(tmp_path)
    write(
        root,
        "projection/deck_plan.yaml",
        {"version": 1, "deck": {"pages": [{"title": "missing id"}]}},
    )
    assert any(f.check == "schema" for f in run_all(root))
    write(root, "projection/deck_plan.yaml", "version: 1\nversion: 1\n")
    assert load_artifact(root, "deck_plan")[0] is None


def test_derived_refs_and_cycles_checked_without_registry(tmp_path):
    item = {"id": "E003", "source": {"source": "derived", "locator": "derived:(E999)"}}
    findings = validate_sources({"evidence": {"items": [item]}}, tmp_path)
    assert any("missing evidence 'E999'" in f.detail for f in findings)
    item["source"]["locator"] = "derived:(E003)"
    assert any(
        "cycle" in f.detail for f in validate_sources({"evidence": {"items": [item]}}, tmp_path)
    )


def test_derived_formula_is_recomputed(tmp_path):
    root = pipeline(tmp_path)
    data = deepcopy(EVIDENCE)
    data["items"].append(
        {
            "id": "E003",
            "kind": "datum",
            "content": "降幅",
            "source": {"source": "derived", "locator": "derived:(E001,E002)"},
            "value": {"number": 99, "unit": "%"},
            "derived": {"formula": "(E001-E002)/E001*100", "precision": 1},
        }
    )
    assert any(
        f.check == "derived-calculation" and f.severity == "error"
        for f in validate_sources({"evidence": data}, root)
    )
    data["items"][-1]["value"]["number"] = 18.2
    assert not any(f.severity == "error" for f in validate_sources({"evidence": data}, root))


def test_pack_contains_all_direct_and_transitive_refs(tmp_path):
    root = pipeline(tmp_path)
    data = deepcopy(EVIDENCE)
    data["items"].append(
        {
            "id": "E003",
            "kind": "datum",
            "content": "derived",
            "source": {"source": "derived", "locator": "derived:(E002)"},
            "value": {"number": 180, "unit": "ms"},
        }
    )
    write(root, "evidence/evidence.yaml", data)
    deck = deepcopy(DECK)
    deck["deck"]["pages"][0]["metric_cards"] = [{"label": "结果", "value_from": "E003"}]
    write(root, "projection/deck_plan.yaml", deck)
    assert {i["id"] for i in build_pack(root, "deck", "P01")["evidence"]} == {
        "E001",
        "E002",
        "E003",
    }
    plan = deepcopy(REPORT_PLAN)
    plan["sections"][0]["evidence"] = ["E003"]
    write(root, "projection/report_plan.yaml", plan)
    assert {i["id"] for i in build_pack(root, "report", "R01")["evidence"]} == {
        "E001",
        "E002",
        "E003",
    }


def test_each_projection_accounts_for_its_own_coverage():
    artifacts = {
        "narrative": NARRATIVE,
        "deck_plan": {"deck": {"pages": []}},
        "report_plan": REPORT_PLAN,
    }
    assert any(f.artifact == "deck_plan" for f in validate_coverage(artifacts))
    artifacts["deck_plan"]["omissions"] = [{"beat": "S01", "reason": "只在报告展开"}]
    assert not any(f.severity == "warn" for f in validate_coverage(artifacts))


def test_manual_hard_constraint_requires_recorded_acceptance(tmp_path):
    brief = deepcopy(BRIEF)
    brief["constraints"] = {
        "hard": [{"id": "tone", "text": "语气自信", "check": "manual", "acceptance": "用户通读"}]
    }
    root = deck_run(tmp_path, brief)
    review(root)
    assert cli(root, "deliver") == 2
    review(root, manual=[{"id": "tone", "verdict": "pass", "detail": "用户确认当前语气"}])
    assert approve(root, "delivery") == 0
    assert cli(root, "deliver") == 0


def test_narrative_rejects_projection_fields():
    data = deepcopy(NARRATIVE)
    data["story"][0]["projection"] = {"status": "dropped"}
    assert validate_schema("narrative", data)


def test_numeric_precision_is_not_silently_rounded():
    evidence = deepcopy(EVIDENCE)
    evidence["items"][0]["value"]["number"] = 0.001
    evidence["items"][0]["content"] = "延迟 0.001 ms"
    narrative = deepcopy(NARRATIVE)
    narrative["claims"][0]["statement"] = "延迟为 0.002 ms"
    assert any(
        f.severity == "error"
        for f in validate_numbers({"evidence": evidence, "narrative": narrative}, None)
    )
    narrative["claims"][0]["statement"] = "延迟为 0.0010 ms"
    assert not any(
        f.severity == "error"
        for f in validate_numbers({"evidence": evidence, "narrative": narrative}, None)
    )


def test_theme_edit_reloads_in_same_process_and_run_override_wins(tmp_path):
    from comh.render.theme import available_themes

    theme = yaml.safe_load(
        (Path(__file__).parents[2] / "themes/tier1-light/theme.yaml").read_text()
    )
    theme["colors"]["accent"] = "00897B"
    write(tmp_path, "themes/tier1-light/theme.yaml", theme)
    assert str(available_themes(tmp_path)["tier1-light"].accent) == "00897B"
    theme["colors"]["accent"] = "B91C1C"
    write(tmp_path, "themes/tier1-light/theme.yaml", theme)
    assert str(available_themes(tmp_path)["tier1-light"].accent) == "B91C1C"


def test_style_relaxation_preserves_explicit_forbidden_words():
    from comh.style_lint import validate_style

    brief = deepcopy(BRIEF)
    brief["voice"] = {"rules": {"relax": ["metaphor"], "extra_forbidden": ["禁止词"]}}
    deck = deepcopy(DECK)
    deck["deck"]["pages"][0]["title"] = "靶点 禁止词"
    findings = validate_style({"brief": brief, "deck_plan": deck}, None)
    assert not any(f.check == "style:metaphor" for f in findings)
    assert any(f.check == "style:forbidden-word" and f.severity == "error" for f in findings)


def test_checked_in_sample_passes_mechanical_contracts():
    root = Path(__file__).parents[2] / "runs/sample-cache-latency"
    assert not [f for f in run_all(root) if f.severity == "error"]


def test_hidden_metadata_cannot_satisfy_content_requirements():
    from comh.report_checks import validate_report
    from comh.validate import validate_hard_constraints

    deck = deepcopy(DECK)
    deck["deck"]["pages"][0]["support_points"] = [{"point": "测试结果", "comment": "局限性"}]
    brief = deepcopy(BRIEF)
    brief["constraints"] = {"hard": ["必须包含:局限性"]}
    assert any(
        f.severity == "error"
        for f in validate_hard_constraints({"brief": brief, "deck_plan": deck}, None)
    )
    text = REPORT.replace("测量边界：受控负载。", "![示意图](../assets/测量边界.png)")
    assert any(
        f.check == "report-contract"
        for f in validate_report({"evidence": EVIDENCE, "report_plan": REPORT_PLAN}, text)
    )


def test_content_page_cannot_omit_its_beat(tmp_path):
    root = pipeline(tmp_path)
    deck = deepcopy(DECK)
    del deck["deck"]["pages"][0]["beat"]
    write(root, "projection/deck_plan.yaml", deck)
    assert cli(root, "save", "deck_plan") == 2

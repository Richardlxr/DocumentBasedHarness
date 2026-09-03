"""Cross-stage regressions found during the end-to-end workflow review."""

from copy import deepcopy

import pytest
from test_appearance_dialogue import styled_run
from test_dialogue import answer, cli, until_outline, until_story, write
from test_workflow_integrity import BRIEF, DECK, REPORT, REPORT_PLAN, review
from workflow_helpers import aligned, approve, simulated_reader

from comh.context import next_action
from comh.dialogue import valid
from comh.manifest import Manifest


@pytest.mark.parametrize("native", [True, False])
def test_rejected_appearance_cannot_enter_review_using_an_existing_build(tmp_path, native):
    root = styled_run(tmp_path) if native else until_outline(tmp_path)
    if not native:
        assert approve(root, "deck_outline") == 0
    assert cli(root, "render", "deck", "--preview") == 0
    assert approve(root, "deck_appearance") == 0
    assert cli(root, "render", "deck") == 0

    summary = root / ".workspace/reconsider.md"
    summary.write_text("Fixture user requests a second look at this appearance.")
    assert cli(root, "present", "deck_appearance", "--summary", str(summary)) == 0
    assert cli(root, "render", "deck") == 2  # The reopened proposal is still awaiting a reply.
    assert answer(root, "deck_appearance", "changes_requested") == 0
    manifest = Manifest.load(root)
    assert not valid(manifest, "deck_appearance")
    manifest.require_build("deck")  # Bytes and source did not change, but consent did.

    review = root / ".workspace/review.yaml"
    write(
        root,
        ".workspace/review.yaml",
        {
            "completed_checks": ["narrative", "audience", "reader", "style"],
            "reader_test": simulated_reader(root),
            "findings": [],
        },
    )
    assert cli(root, "review", str(review)) == 2
    assert not (root / "qa/model-findings.yaml").exists()
    assert cli(root, "present", "delivery") == 2

    # Only a new, scoped acceptance restores eligibility; build bytes can be reused.
    assert approve(root, "deck_appearance") == 0
    assert cli(root, "review", str(review)) == 0


@pytest.mark.parametrize("due, expected", [("authoring", 2), ("qa", 0)])
def test_report_save_checks_questions_due_at_authoring(tmp_path, capsys, due, expected):
    brief = aligned({**BRIEF, "media": [{"medium": "markdown", "surface": "report"}]})
    brief["open_questions"] = [
        {
            "question": "报告正文用哪一版补充材料？",
            "status": "deferred",
            "due": due,
            "reason": "先确定研究问题与大纲，再决定补充材料范围。",
        }
    ]
    root = until_story(tmp_path, brief)
    assert approve(root, "narrative") == 0
    write(root, "projection/report_plan.yaml", REPORT_PLAN)
    assert cli(root, "save", "report_plan") == 0
    assert approve(root, "report_outline") == 0
    write(root, "documents/report.md", REPORT)
    assert cli(root, "save", "report_md") == expected
    if expected:
        assert "报告正文用哪一版补充材料" in capsys.readouterr().err
        assert Manifest.load(root).artifact_state("report_md").state == "unsaved"


def test_collaborative_academic_multi_output_lifecycle_and_local_revision(tmp_path):
    brief = aligned(
        {
            **BRIEF,
            "presentation": {"setting": "academic"},
            "media": [
                {"medium": "pptx", "surface": "presentation"},
                {"medium": "html", "surface": "presentation"},
                {"medium": "docx", "surface": "report"},
            ],
        }
    )
    root = until_outline(tmp_path, brief)
    assert cli(
        root, "collaborate", "collaborative", "--reply", "逐页逐节打磨", "--source", "test:user"
    ) == 0
    assert approve(root, "deck_outline") == 0
    assert cli(root, "render", "deck") == 2
    assert approve(root, "deck_detail", "P01") == 0
    write(root, "projection/report_plan.yaml", REPORT_PLAN)
    assert cli(root, "save", "report_plan") == 0
    assert approve(root, "report_outline") == 0
    write(root, "documents/report.md", REPORT)
    assert cli(root, "save", "report_md") == 2
    assert approve(root, "report_detail", "R01") == 0
    assert cli(root, "save", "report_md") == 0
    for target in ("deck", "deck-html", "report"):
        assert cli(root, "render", target) == 0
    review(root)  # Explicit synthetic reader fixture; tests the receipt protocol only.
    assert approve(root, "delivery") == 0
    assert cli(root, "deliver") == 0
    manifest = Manifest.load(root)
    assert manifest.output_selection() == {"deck", "deck_html", "report_docx", "report_md"}
    assert next_action(manifest)["action"] == "complete"

    # A content-only page change keeps the story/outline and report decisions,
    # but must get a new page decision and cannot reuse delivery acceptance.
    plan = deepcopy(DECK)
    plan["deck"]["pages"][0]["support_points"] = ["基线实验的测量说明"]
    write(root, "projection/deck_plan.yaml", plan)
    assert cli(root, "save", "deck_plan") == 0
    manifest = Manifest.load(root)
    assert manifest.gate_valid("narrative")
    assert valid(manifest, "deck_outline") and valid(manifest, "report_detail", "R01")
    assert not valid(manifest, "deck_detail", "P01")
    assert manifest.delivery_state()[0] == "invalidated"
    assert cli(root, "deliver") == 2
    assert cli(root, "render", "deck") == 2
    assert approve(root, "deck_detail", "P01") == 0
    for target in ("deck", "deck-html"):
        assert cli(root, "render", target) == 0
    Manifest.load(root).require_build("report_docx")
    review(root)
    assert approve(root, "delivery") == 0
    assert cli(root, "deliver") == 0

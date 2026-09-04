"""User decisions, stage recovery, outline refinement and bounded context integration."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from test_workflow_integrity import BRIEF, DECK, EVIDENCE, NARRATIVE, REPORT, REPORT_PLAN
from workflow_helpers import aligned, approve, prepare

from comh.cli import main
from comh.context import context_pack, instructions, next_action
from comh.decision_checks import brief_errors, narrative_errors
from comh.dialogue import latest, respond, set_mode, valid
from comh.evidence_pack import build_pack
from comh.manifest import Manifest, RunError
from comh.scaffold import init_run


def write(root, key, value):
    path = root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else yaml.safe_dump(value, allow_unicode=True))


def cli(root, *args):
    return main([*args, "--run", str(root)])


def until_brief(tmp_path, brief=None):
    root = init_run(tmp_path / "run")
    write(root, "sources/data.csv", "latency_ms\n220\n180\n")
    prepare(root)
    write(root, "evidence/evidence.yaml", EVIDENCE)
    write(root, "brief/brief.yaml", aligned(BRIEF) if brief is None else brief)
    assert cli(root, "save", "evidence") == 0
    assert cli(root, "save", "brief") == 0
    return root


def until_story(tmp_path, brief=None, narrative=None):
    root = until_brief(tmp_path, brief)
    assert approve(root, "brief") == 0
    write(root, "narrative/narrative.yaml", narrative or NARRATIVE)
    assert cli(root, "save", "narrative") == 0
    return root


def until_outline(tmp_path, brief=None, deck=None):
    root = until_story(tmp_path, brief)
    assert approve(root, "narrative") == 0
    write(root, "projection/deck_plan.yaml", deck or DECK)
    assert cli(root, "save", "deck_plan") == 0
    return root


def answer(root, target, decision="accepted", node=None):
    r = latest(Manifest.load(root), target, node)
    return cli(
        root,
        "respond",
        r["id"],
        "--decision",
        decision,
        "--reply",
        "当前用户回复",
        "--source",
        "test:user-message",
    )


def test_new_run_starts_with_intake_and_installed_instructions(tmp_path):
    root = init_run(tmp_path / "run")
    assert next_action(Manifest.load(root)) == {"stage": "intake", "action": "record_intake"}
    assert context_pack(Manifest.load(root))["instructions"]["hash"]
    assert cli(root, "instructions", "skill", "--json") == 0
    assert Path(instructions("projection")["path"]).is_file()


def test_bare_confirm_and_wrong_request_do_not_accept(tmp_path):
    root = until_brief(tmp_path)
    assert cli(root, "confirm", "brief") == 2
    assert cli(root, "present", "brief") == 0
    assert (
        cli(
            root,
            "confirm",
            "brief",
            "--request",
            "D9999",
            "--reply",
            "yes",
            "--source",
            "test:user",
        )
        == 2
    )
    assert not Manifest.load(root).gate_valid("brief")
    r = latest(Manifest.load(root), "brief")
    assert (
        cli(
            root,
            "confirm",
            "brief",
            "--request",
            r["id"],
            "--reply",
            "yes",
            "--source",
            "test:user",
        )
        == 0
    )


@pytest.mark.parametrize(
    "change",
    ["missing_alignment", "unanswered", "inferred_as_user", "wrong_value", "missing_coverage"],
)
def test_incomplete_contract_is_a_draft_not_an_accepted_decision(tmp_path, change):
    brief = aligned(BRIEF)
    if change == "missing_alignment":
        del brief["alignment"]["voice"]
    elif change == "unanswered":
        brief["open_questions"] = [{"question": "内部还是外部受众？"}]
    elif change == "inferred_as_user":
        brief["alignment"]["audience"]["source"] = "inference"
    elif change == "wrong_value":
        brief["alignment"]["objective"]["value"] = "另一个目标"
    root = until_brief(tmp_path, brief)
    if change == "missing_coverage":
        (root / "evidence/coverage.yaml").unlink()
    assert cli(root, "present", "brief") == 0
    assert latest(Manifest.load(root), "brief")["blockers"]
    assert answer(root, "brief") == 2
    assert not Manifest.load(root).gate_valid("brief")


def test_proposed_default_can_be_accepted_without_fake_prior_answers(tmp_path):
    brief = aligned(BRIEF)
    brief["alignment"]["voice"].update(source="default", status="proposed", basis="建议直白语气")
    root = until_brief(tmp_path, brief)
    assert approve(root, "brief") == 0
    assert Manifest.load(root).gate_valid("brief")


def test_deferred_question_is_checked_at_its_deadline(tmp_path):
    brief = aligned(BRIEF)
    brief["open_questions"] = [
        {
            "question": "图表形式？",
            "status": "deferred",
            "due": "projection",
            "reason": "先确认故事",
        }
    ]
    root = until_story(tmp_path, brief)
    assert approve(root, "narrative") == 0
    write(root, "projection/deck_plan.yaml", DECK)
    assert cli(root, "save", "deck_plan") == 0
    assert cli(root, "present", "deck_outline") == 0
    assert answer(root, "deck_outline") == 2
    assert not brief_errors(brief)
    assert brief_errors(brief, "projection")


def test_stale_reply_cannot_accept_revised_proposal_and_retries_are_idempotent(tmp_path):
    root = until_brief(tmp_path)
    assert cli(root, "present", "brief") == 0
    old = latest(Manifest.load(root), "brief")["id"]
    brief = aligned(BRIEF)
    brief["objective"] = "只评估适用边界"
    brief = aligned(brief)
    write(root, "brief/brief.yaml", brief)
    assert cli(root, "save", "brief") == 0
    assert answer(root, "brief") == 2
    assert cli(root, "present", "brief") == 0
    assert latest(Manifest.load(root), "brief")["id"] != old
    assert (
        cli(
            root, "respond", old, "--decision", "accepted", "--reply", "yes", "--source", "test:old"
        )
        == 2
    )
    assert answer(root, "brief") == 0
    before = (root / "run.yaml").read_bytes()
    assert answer(root, "brief") == 0
    assert (root / "run.yaml").read_bytes() == before


def test_story_cannot_be_skipped_by_refinement_delegation(tmp_path):
    root = until_story(tmp_path)
    assert cli(root, "present", "narrative") == 0
    set_mode(Manifest.load(root), "delegated", "不用逐页磨", "test:user")
    assert answer(root, "narrative", "delegated") == 2
    write(root, "projection/deck_plan.yaml", DECK)
    assert cli(root, "save", "deck_plan") == 2
    assert next_action(Manifest.load(root))["action"] == "await_user"


def test_unknown_claim_needs_a_disclosed_disposition(tmp_path):
    narrative = deepcopy(NARRATIVE)
    narrative["claims"][0].update(
        status="needs_research", evidence=[], importance="primary", statement="机制尚不确定"
    )
    narrative["story"][0]["message"] = "机制尚不确定"
    root = until_story(tmp_path, narrative=narrative)
    assert cli(root, "present", "narrative") == 0
    assert answer(root, "narrative") == 2
    narrative["claims"][0]["resolution"] = {
        "action": "qualify",
        "reason": "说明当前缺口",
        "boundary": "不能声称已证明机制",
    }
    write(root, "narrative/narrative.yaml", narrative)
    assert cli(root, "save", "narrative") == 0
    assert approve(root, "narrative") == 0
    assert (
        latest(Manifest.load(root), "narrative")["view"]["claims"][0]["status"] == "needs_research"
    )


def test_outline_blocks_render_and_ignores_pure_theme_changes(tmp_path):
    root = until_outline(tmp_path)
    assert cli(root, "render", "deck") == 2
    assert not (root / "build/deck.pptx").exists()
    assert approve(root, "deck_outline") == 0
    deck = deepcopy(DECK)
    deck["deck"]["style"] = {"template": "slate-tech"}
    write(root, "projection/deck_plan.yaml", deck)
    assert cli(root, "save", "deck_plan") == 0
    assert valid(Manifest.load(root), "deck_outline")
    assert cli(root, "render", "deck") == 2
    assert cli(root, "render", "deck", "--preview") == 0
    assert approve(root, "deck_appearance") == 0
    assert cli(root, "render", "deck") == 0
    deck["deck"]["pages"][0]["title"] = "新的结构重点"
    write(root, "projection/deck_plan.yaml", deck)
    assert cli(root, "save", "deck_plan") == 0
    assert not valid(Manifest.load(root), "deck_outline")
    assert cli(root, "render", "deck") == 2


def test_draft_can_present_outline_but_cannot_render(tmp_path):
    deck = {**deepcopy(DECK), "draft": True}
    root = until_outline(tmp_path, deck=deck)
    assert approve(root, "deck_outline") == 0
    assert cli(root, "render", "deck") == 2
    deck["draft"] = False
    write(root, "projection/deck_plan.yaml", deck)
    assert cli(root, "save", "deck_plan") == 0
    assert valid(Manifest.load(root), "deck_outline")
    assert cli(root, "render", "deck") == 0


def test_collaborative_mode_requires_each_page_but_user_can_change_mode(tmp_path):
    deck = deepcopy(DECK)
    deck["deck"]["pages"].append({**deck["deck"]["pages"][0], "id": "P02"})
    root = until_outline(tmp_path, deck=deck)
    set_mode(Manifest.load(root), "collaborative", "一起逐页磨", "test:user")
    assert approve(root, "deck_outline") == 0
    assert cli(root, "render", "deck") == 2
    assert approve(root, "deck_detail", "P01") == 0
    assert next_action(Manifest.load(root))["node"] == "P02"
    assert cli(root, "present", "deck_detail", "--node", "P02") == 0
    assert cli(root, "render", "deck") == 2
    set_mode(Manifest.load(root), "checkpoints", "剩余页不用逐页磨", "test:user")
    assert cli(root, "render", "deck") == 0


def test_report_prose_requires_its_own_outline(tmp_path):
    brief = aligned({**BRIEF, "media": [{"medium": "markdown", "surface": "report"}]})
    root = until_story(tmp_path, brief)
    assert approve(root, "narrative") == 0
    write(root, "projection/report_plan.yaml", REPORT_PLAN)
    assert cli(root, "save", "report_plan") == 0
    write(root, "documents/report.md", REPORT)
    assert cli(root, "save", "report_md") == 2
    assert approve(root, "report_outline") == 0
    assert cli(root, "save", "report_md") == 0
    assert next_action(Manifest.load(root))["action"] == "review"


def test_resume_preserves_rejection_and_pending_request(tmp_path):
    root = until_story(tmp_path)
    assert cli(root, "present", "narrative") == 0
    assert answer(root, "narrative", "changes_requested") == 0
    assert cli(root, "present", "narrative") == 0
    r = latest(Manifest.load(root), "narrative")
    pack = context_pack(Manifest.load(root))
    assert pack["next"]["request_id"] == r["id"]
    assert pack["next"]["action"] == "await_user"
    assert any(d["state"] == "changes_requested" for d in pack["decisions"])
    assert pack["contract"]["objective"] == BRIEF["objective"]
    assert cli(root, "context", "--max-chars", "1") == 2


def test_counterevidence_is_in_local_slice_and_context(tmp_path):
    narrative = deepcopy(NARRATIVE)
    narrative["claims"][0]["counterevidence"] = ["E002"]
    root = until_story(tmp_path, narrative=narrative)
    assert {e["id"] for e in build_pack(root, "narrative", "S01")["evidence"]} == {"E001", "E002"}
    pack = context_pack(Manifest.load(root), "narrative", "S01")
    assert pack["slice"]["claims"][0]["counterevidence"] == ["E002"]
    assert pack["contract"]["constraints"]


def test_legacy_confirmation_is_preserved_but_not_trusted(tmp_path):
    root = until_brief(tmp_path)
    manifest = Manifest.load(root)
    legacy = {"confirmed": True, "at": "old", "hash": manifest._current_hash("brief")}
    manifest.data["gates"]["brief"] = legacy
    manifest.data.pop("interaction")
    manifest.save()
    loaded = Manifest.load(root)
    assert not loaded.gate_valid("brief")
    assert loaded.data["gates"]["brief"] == legacy
    assert context_pack(loaded)["gates"]["brief"]["legacy"]
    with pytest.raises(RunError):
        loaded.confirm_gate("brief")


def test_missing_or_blank_response_source_rejected_without_mutation(tmp_path):
    root = until_brief(tmp_path)
    assert cli(root, "present", "brief") == 0
    manifest = Manifest.load(root)
    r = latest(manifest, "brief")
    with pytest.raises(RunError):
        respond(manifest, r["id"], "accepted", "yes", " ")
    assert not manifest.gate_valid("brief")


def test_upstream_change_supersedes_obsolete_pending_request(tmp_path):
    root = until_outline(tmp_path)
    assert cli(root, "present", "deck_outline") == 0
    old = latest(Manifest.load(root), "deck_outline")["id"]
    brief = aligned({**BRIEF, "objective": "重新检查适用范围"})
    write(root, "brief/brief.yaml", brief)
    assert cli(root, "save", "brief") == 0
    assert approve(root, "brief") == 0
    history = Manifest.load(root).data["interaction"]["requests"]
    assert next(r for r in history if r["id"] == old)["state"] == "superseded"


def test_semantically_identical_gate_edit_can_receive_new_acceptance(tmp_path):
    root = until_story(tmp_path)
    assert approve(root, "narrative") == 0
    old = latest(Manifest.load(root), "narrative")["id"]
    path = root / "narrative/narrative.yaml"
    path.write_text(path.read_text() + "# changed bytes\n")
    assert cli(root, "save", "narrative") == 0
    assert not Manifest.load(root).gate_valid("narrative")
    assert approve(root, "narrative") == 0
    assert latest(Manifest.load(root), "narrative")["id"] != old
    assert Manifest.load(root).gate_valid("narrative")


def test_valid_pending_request_cannot_be_overwritten_by_another_target(tmp_path):
    root = until_outline(tmp_path)
    assert approve(root, "deck_outline") == 0
    assert cli(root, "present", "deck_detail", "--node", "P01") == 0
    summary = root / ".workspace/new-summary.md"
    summary.write_text("另一提案")
    assert cli(root, "present", "brief", "--summary", str(summary)) == 2
    assert latest(Manifest.load(root), "deck_detail", "P01")["state"] == "awaiting_user"


def test_preview_is_not_a_build_and_does_not_invalidate_formal_outputs(tmp_path):
    root = until_outline(tmp_path)
    assert approve(root, "deck_outline") == 0
    assert cli(root, "render", "deck") == 0
    before = (root / "run.yaml").read_bytes()
    assert cli(root, "render", "deck", "--preview") == 0
    assert (root / ".workspace/preview-deck.pptx").is_file()
    assert before == (root / "run.yaml").read_bytes()
    Manifest.load(root).require_build("deck")
    set_mode(Manifest.load(root), "collaborative", "逐页确认", "test:user")
    assert cli(root, "render", "deck", "--preview") == 0
    assert cli(root, "render", "deck") == 2


def test_report_detail_additions_preserve_coarse_outline(tmp_path):
    brief = aligned({**BRIEF, "media": [{"medium": "markdown", "surface": "report"}]})
    root = until_story(tmp_path, brief)
    assert approve(root, "narrative") == 0
    plan = deepcopy(REPORT_PLAN)
    write(root, "projection/report_plan.yaml", plan)
    assert cli(root, "save", "report_plan") == 0
    assert approve(root, "report_outline") == 0
    plan["sections"][0]["depth"] = "full explanation"
    write(root, "projection/report_plan.yaml", plan)
    assert cli(root, "save", "report_plan") == 0
    assert valid(Manifest.load(root), "report_outline")


def test_malformed_downstream_draft_remains_recoverable(tmp_path):
    root = until_brief(tmp_path)
    write(root, "narrative/narrative.yaml", "broken: [")
    pack = context_pack(Manifest.load(root))
    assert pack["next"]["target"] == "brief"
    assert pack["load_errors"][0]["artifact"] == "narrative"
    assert cli(root, "context") == 0


def test_intake_question_cannot_disappear_or_use_null_as_answer(tmp_path):
    root = until_brief(tmp_path)
    manifest = Manifest.load(root)
    intake_data = manifest.data["interaction"]["intake"]
    intake_data["open_questions"] = [{"question": "关键受众？", "answer": None}]
    path = root / ".workspace/intake.yaml"
    write(root, path.relative_to(root), intake_data)
    assert cli(root, "intake", str(path)) == 0
    assert cli(root, "present", "brief") == 0
    assert answer(root, "brief") == 2
    intake_data["open_questions"] = ["bad entry"]
    write(root, path.relative_to(root), intake_data)
    assert cli(root, "intake", str(path)) == 2


def test_reader_checkbox_without_output_cannot_complete_qa(tmp_path):
    from test_workflow_integrity import deck_run

    root = deck_run(tmp_path)
    review = root / ".workspace/review.yaml"
    write(
        root,
        review.relative_to(root),
        {
            "completed_checks": ["narrative", "audience", "reader", "style"],
            "findings": [],
        },
    )
    assert cli(root, "review", str(review)) == 2
    assert not (root / "qa/model-findings.yaml").exists()


def test_delivery_acceptance_pins_review_and_reader_output(tmp_path):
    from test_workflow_integrity import deck_run, review

    root = deck_run(tmp_path)
    review(root)
    assert cli(root, "present", "delivery") == 0
    path = root / "qa/model-findings.yaml"
    path.write_text(path.read_text() + "# re-reviewed\n")
    assert answer(root, "delivery") == 2
    assert approve(root, "delivery") == 0
    assert cli(root, "deliver") == 0
    before = (root / "run.yaml").read_bytes()
    assert cli(root, "deliver") == 0
    assert before == (root / "run.yaml").read_bytes()
    (root / "qa/reader-output.md").write_text("Reader output changed.")
    assert Manifest.load(root).delivery_state()[0] == "invalidated"
    assert cli(root, "deliver") == 2


def test_custom_uncertainty_status_still_needs_disposition():
    narrative = deepcopy(NARRATIVE)
    narrative["claims"][0]["status"] = "disputed"
    assert narrative_errors(narrative)
    narrative["claims"][0]["resolution"] = {
        "action": "qualify",
        "reason": "存在争议",
        "boundary": "不能视为确定结论",
    }
    assert not narrative_errors(narrative)


def test_context_keeps_older_rejections_outside_recent_history(tmp_path):
    root = until_brief(tmp_path)
    assert cli(root, "present", "brief") == 0
    assert answer(root, "brief", "changes_requested") == 0
    manifest = Manifest.load(root)
    first = manifest.data["interaction"]["requests"][0]
    manifest.data["interaction"]["requests"].extend(
        {**deepcopy(first), "id": f"D{i:04d}", "state": "superseded"} for i in range(2, 15)
    )
    manifest.save()
    pack = context_pack(Manifest.load(root))
    assert pack["history_omitted"] == 2
    assert pack["older_rejections"][0]["response"]["decision"] == "changes_requested"


def test_repository_skill_discovery_entry_is_windows_checkout_safe():
    root = Path(__file__).resolve().parents[2]
    entry = root / ".agents/skills/communication-harness/SKILL.md"
    canonical = root / "comh/instructions/skill/SKILL.md"

    assert entry.is_file()
    assert not entry.is_symlink()
    assert canonical.is_file()
    assert "../../../comh/instructions/skill/SKILL.md" in entry.read_text(encoding="utf-8")

"""Template intent, sample acceptance and scoped reuse through the real CLI."""

from copy import deepcopy
from shutil import copytree

import pytest
import yaml
from test_dialogue import answer, cli, until_brief, until_outline, write
from test_pptx_style import fixture
from test_workflow_integrity import BRIEF, DECK
from workflow_helpers import aligned, approve

from comh.appearance import needs_review, preview_errors, signature
from comh.context import next_action
from comh.dialogue import latest, valid
from comh.manifest import Manifest, RunError


def styled_run(tmp_path, policy=None):
    brief = deepcopy(BRIEF)
    brief["appearance"] = policy or {
        "selection": "specified",
        "reference": "templates/brand/style.yaml",
        "review": "sample",
    }
    root = until_outline(tmp_path, aligned(brief))
    native = tmp_path / "native"
    native.mkdir()
    _, sample, _ = fixture(native)
    copytree(sample / "templates/brand", root / "templates/brand")
    deck = deepcopy(DECK)
    deck["deck"]["style"] = {"pptx_style": "templates/brand/style.yaml"}
    write(root, "projection/deck_plan.yaml", deck)
    assert cli(root, "save", "deck_plan") == 0
    assert approve(root, "deck_outline") == 0
    return root


def test_pptx_intent_is_required_but_report_does_not_ask(tmp_path):
    brief = aligned(BRIEF)
    del brief["appearance"], brief["alignment"]["appearance"]
    root = until_brief(tmp_path, brief)
    assert approve(root, "brief") == 2
    brief["media"] = [{"medium": "markdown", "surface": "report"}]
    brief["alignment"]["media"]["value"] = brief["media"]
    write(root, "brief/brief.yaml", brief)
    assert cli(root, "save", "brief") == 0
    assert approve(root, "brief") == 0
    assert not needs_review(Manifest.load(root))


def test_native_choice_still_needs_sample_before_bulk_render(tmp_path):
    root = styled_run(tmp_path)
    assert next_action(Manifest.load(root))["action"] == "render_preview"
    assert cli(root, "render", "deck") == 2
    assert approve(root, "deck_appearance") == 2
    assert cli(root, "render", "deck", "--preview") == 0
    assert next_action(Manifest.load(root))["target"] == "deck_appearance"
    assert approve(root, "deck_appearance") == 0
    assert cli(root, "render", "deck") == 0
    assert not preview_errors(Manifest.load(root))


def test_outline_delegation_does_not_delegate_appearance(tmp_path):
    root = styled_run(tmp_path)
    summary = root / ".workspace/outline-summary.md"
    summary.write_text("用户委托细化")
    assert cli(root, "present", "deck_outline", "--summary", str(summary)) == 0
    assert answer(root, "deck_outline", "delegated") == 0
    assert cli(root, "render", "deck") == 2
    assert cli(root, "render", "deck", "--preview") == 0
    assert approve(root, "deck_appearance") == 0
    assert cli(root, "render", "deck") == 0


def test_explicit_appearance_delegation_allows_render(tmp_path):
    root = styled_run(tmp_path, {"selection": "delegated", "review": "delegated"})
    assert not needs_review(Manifest.load(root))
    assert cli(root, "render", "deck") == 0
    assert latest(Manifest.load(root), "deck_appearance") is None


@pytest.mark.parametrize("selection", ["deferred", "specified"])
def test_later_choice_or_changed_choice_is_reviewed_after_outline(tmp_path, selection):
    policy = {"selection": selection, "review": "delegated"}
    if selection == "specified":
        policy["reference"] = "slate-tech"
    root = styled_run(tmp_path, policy)
    assert Manifest.load(root).gate_valid("narrative")
    assert cli(root, "render", "deck") == 2
    assert cli(root, "render", "deck", "--preview") == 0
    assert approve(root, "deck_appearance") == 0
    record = latest(Manifest.load(root), "deck_appearance")
    assert bool(record["view"]["changes_from_brief"]) == (selection == "specified")
    assert cli(root, "render", "deck") == 0


def test_content_and_wrap_repairs_reuse_appearance_but_dirty_build(tmp_path):
    root = styled_run(tmp_path)
    assert cli(root, "render", "deck", "--preview") == 0
    assert approve(root, "deck_appearance") == 0
    assert cli(root, "render", "deck") == 0
    manifest = Manifest.load(root)
    original = signature(manifest)
    path = root / "projection/deck_plan.yaml"
    plan = yaml.safe_load(path.read_text())
    plan["deck"]["pages"][0]["support_points"] = ["补充实验说明"]
    write(root, "projection/deck_plan.yaml", plan)
    assert cli(root, "save", "deck_plan") == 0
    assert valid(Manifest.load(root), "deck_appearance")
    assert cli(root, "render", "deck") == 0
    profile = root / "templates/brand/style.yaml"
    data = yaml.safe_load(profile.read_text())
    data["surfaces"]["content"]["single_line"] = {"slide": []}
    profile.write_text(yaml.safe_dump(data))
    manifest = Manifest.load(root)
    assert signature(manifest) == original
    assert valid(manifest, "deck_appearance")
    with pytest.raises(RunError):
        manifest.require_build("deck")


@pytest.mark.parametrize("change", ["tokens", "keep", "disclosure"])
def test_material_appearance_changes_invalidate_only_appearance(tmp_path, change):
    root = styled_run(tmp_path)
    assert cli(root, "render", "deck", "--preview") == 0
    assert approve(root, "deck_appearance") == 0
    if change == "disclosure":
        path = root / "projection/deck_plan.yaml"
        plan = yaml.safe_load(path.read_text())
        plan["deck"]["appearance_review"] = {"summary": "字体替换", "adjustments": ["Arial"]}
        path.write_text(yaml.safe_dump(plan))
        assert cli(root, "save", "deck_plan") == 0
    else:
        path = root / "templates/brand/style.yaml"
        profile = yaml.safe_load(path.read_text())
        if change == "tokens":
            profile["tokens"]["sizes"]["content_title"] = 30
        else:
            profile["surfaces"]["content"]["keep"]["slide"] = []
            profile["surfaces"]["content"]["protect"] = {}
        path.write_text(yaml.safe_dump(profile))
    manifest = Manifest.load(root)
    assert manifest.gate_valid("narrative") and valid(manifest, "deck_outline")
    assert not valid(manifest, "deck_appearance")
    assert preview_errors(manifest)
    assert cli(root, "render", "deck") == 2


def test_pending_sample_is_pinned_and_cannot_be_replaced_without_showing_it(tmp_path):
    root = styled_run(tmp_path)
    assert cli(root, "render", "deck", "--preview") == 0
    assert cli(root, "present", "deck_appearance") == 0
    old = latest(Manifest.load(root), "deck_appearance")["id"]
    preview = root / ".workspace/preview-deck.pptx"
    preview.write_bytes(b"tampered")
    assert answer(root, "deck_appearance") == 2
    path = root / "projection/deck_plan.yaml"
    plan = yaml.safe_load(path.read_text())
    plan["deck"]["pages"][0]["support_points"] = ["新的样张内容"]
    path.write_text(yaml.safe_dump(plan))
    assert cli(root, "save", "deck_plan") == 0
    assert cli(root, "render", "deck", "--preview") == 0
    assert not preview_errors(Manifest.load(root))
    assert answer(root, "deck_appearance") == 2
    assert cli(root, "present", "deck_appearance") == 0
    assert latest(Manifest.load(root), "deck_appearance")["id"] != old
    assert answer(root, "deck_appearance") == 0

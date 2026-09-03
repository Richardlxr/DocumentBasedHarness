from copy import deepcopy

import pytest
from test_dialogue import cli, until_outline, write
from test_workflow_integrity import DECK
from workflow_helpers import approve

from comh.audience_lint import lint_surface, validate_audience_copy
from comh.style_lint import validate_style
from comh.visible_text import page_texts

BAD = "应用层结论：委托方最终关心的价值"


@pytest.mark.parametrize(
    "text",
    [
        BAD,
        "前置门槛：先立住工具，结论才有意义",
        "机制层结论：Arm MPAM 方向研究的直接产出",
        "本页目的：让甲方认可研究",
        "本页用于说服客户",
        "&#x20;",
    ],
)
def test_internal_framing_and_encoded_entities_are_errors(text):
    found = lint_surface("deck_plan", "P01 title", text, {})
    assert any(f.severity == "error" and f.verdict == "fail" for f in found)


@pytest.mark.parametrize(
    "text",
    [
        "甲方要求逐周期时延低于目标值",
        "适用边界：当前结果来自功能仿真，真实设备效果仍需验证。",
        "机制层结论：缓存分区降低了本实验的干扰损失",
        "客户关心的是设备能否稳定运行。",
        "接口语义验证：相同配置产生相同结果。",
        "本研究的直接产出包括实验脚本和对照数据。",
    ],
)
def test_domain_terms_actual_limits_and_legitimate_customer_references_are_not_banned(text):
    assert not lint_surface("deck_plan", "P01 title", text, {})


def test_compressed_boundaries_and_assurance_are_review_warnings():
    text = "适用边界：功能级模型 · 单通道单路 · 乱序模型校准阶段 · 合成负载"
    assert {f.check for f in lint_surface("deck_plan", "P13 callout", text, {})} == {
        "audience:compressed-boundary"
    }
    text = "同配置重跑结果逐位一致（确定性自洽）；完全重叠 = 无隔离语义验证通过"
    assert all(f.severity == "warn" for f in lint_surface("deck_plan", "P13 callout", text, {}))


def page_with_all_visible_surfaces():
    return {
        "id": "P01",
        "title": BAD,
        "kicker": BAD,
        "support_points": [{"point": BAD, "detail": BAD}],
        "metric_cards": [{"label": BAD, "value_from": "E001"}],
        "callout": {"text": BAD},
        "visual": {
            "columns": [BAD, "正常对照"],
            "chart": {"series": [{"label": BAD}]},
            "asset_refs": [{"ref": "asset.png", "caption": BAD}],
            "diagram": {
                "mermaid": f'flowchart LR\n A["{BAD}"] -->|{BAD}| B[正常节点]',
                "caption": BAD,
            },
        },
    }


def test_all_authored_visible_fields_are_checked_but_private_planning_is_not():
    page = page_with_all_visible_surfaces()
    fields = {field for field, text in page_texts(page) if BAD in text}
    assert len(fields) == 12
    artifacts = {
        "brief": {"voice": {"style": "punchy", "rules": {"relax": ["planning-leak"]}}},
        "deck_plan": {"deck": {"pages": [page]}},
    }
    found = validate_audience_copy(artifacts, None)
    assert sum(f.check == "audience:planning-leak" for f in found) == len(fields)
    # Explicit forbidden words get the same complete field coverage as audience rules.
    artifacts["brief"]["voice"]["rules"]["extra_forbidden"] = ["委托方"]
    assert sum(f.check == "style:forbidden-word" for f in validate_style(artifacts, None)) == len(
        fields
    )
    safe = {
        "id": "P02",
        "title": "当前实验的结论",
        "notes": BAD,
        "demotions": [{"content": BAD, "to": "notes"}],
        "visual": {"intent": BAD, "diagram": {"mermaid": f"flowchart LR\n%% {BAD}\nA --> B"}},
    }
    assert not validate_audience_copy({"deck_plan": {"deck": {"pages": [safe]}}}, None)


def test_report_headings_tables_and_narrative_messages_are_checked():
    report = (
        f"# {BAD}\n\n| 项目 | 含义 |\n|---|---|\n| x | {BAD} |\n\n```python\nprint('{BAD}')\n```\n"
    )
    narrative = {"story": [{"id": "S01", "message": BAD, "purpose": "establish_value"}]}
    found = validate_audience_copy({"narrative": narrative}, report)
    assert (
        sum(f.artifact == "report_md" and f.check == "audience:planning-leak" for f in found) == 2
    )
    assert any(f.artifact == "narrative" for f in found)


def test_explicit_teaching_quote_exception_is_exact_scoped_and_auditable():
    entry = {
        "artifact": "deck_plan",
        "location": "P01 title",
        "text": BAD,
        "rule": "audience:planning-leak",
        "reason": "用户要求展示这句作为写作反例",
        "source": "test:user",
    }
    brief = {"audience": {"copy_exceptions": [entry]}}
    found = lint_surface("deck_plan", "P01 title", BAD, brief)
    assert len(found) == 1 and found[0].verdict == "pass" and "反例" in found[0].detail
    assert lint_surface("deck_plan", "P02 title", BAD, brief)[0].severity == "error"
    assert lint_surface("deck_plan", "P01 title", BAD + "。", brief)[0].severity == "error"
    entry["source"] = ""
    assert lint_surface("deck_plan", "P01 title", BAD, brief)[0].severity == "error"


def test_real_cli_blocks_leak_in_caption_before_build_then_accepts_concrete_rewrite(tmp_path):
    root = until_outline(tmp_path)
    assert approve(root, "deck_outline") == 0
    plan = deepcopy(DECK)
    plan["deck"]["pages"][0]["kicker"] = BAD
    write(root, "projection/deck_plan.yaml", plan)
    assert cli(root, "save", "deck_plan") == 2
    assert cli(root, "render", "deck") == 2
    assert not (root / "build/deck.pptx").exists()
    plan["deck"]["pages"][0]["kicker"] = "缓存实验"
    write(root, "projection/deck_plan.yaml", plan)
    assert cli(root, "save", "deck_plan") == 0
    assert cli(root, "render", "deck") == 0

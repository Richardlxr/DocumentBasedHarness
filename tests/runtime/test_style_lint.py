"""AI-tell detector tests (detect -> rewrite -> re-detect loop's detector)."""

from __future__ import annotations

from comh.style_lint import lint_report, lint_text, validate_style


def test_em_dash_punchline_in_title_and_callout() -> None:
    findings = lint_text("P01", "title", "伤害来自缓存共用——分开，就没事")
    checks = {f.check for f in findings}
    assert "style:em-dash" in checks
    assert "style:metaphor" in checks  # 伤害


def test_double_dash_in_points_flags() -> None:
    text = "先说结论——成立；再看数据——稳定"
    findings = lint_text("P02", "support_points[0]", text)
    assert any(f.check == "style:em-dash" for f in findings)


def test_contrast_frame_density() -> None:
    text = "不是延迟问题，而是带宽问题；不是配置问题，而是容量问题"
    findings = lint_text("P03", "callout", text)
    assert any(f.check == "style:contrast-frame" for f in findings)


def test_english_tells() -> None:
    for text in (
        "This is not just a cache — it is a policy layer.",
        "Let us delve into the crucial metrics.",
    ):
        findings = lint_text("P04", "support_points[0]", text)
        assert any(f.check == "style:en-tell" for f in findings), text


def test_plain_text_passes() -> None:
    text = "两条链路完全分开后，干扰没有再出现；瓶颈确认是容量共用"
    assert lint_text("P05", "title", text) == []
    assert lint_report("共享缓存时尾延迟升高。分区后恢复。") == []


def test_validate_style_walks_deck_and_report() -> None:
    artifacts = {
        "deck_plan": {
            "deck": {
                "title": "t",
                "pages": [
                    {
                        "id": "P01",
                        "page_role": "content",
                        "title": "机制可信——硬件待验",
                        "support_points": ["普通要点"],
                        "callout": {"text": "正常结论条"},
                    },
                ],
            }
        },
    }
    findings = validate_style(artifacts, "正文一段。没有问题的段落。")
    assert any(f.check == "style:em-dash" and "P01" in f.detail for f in findings)


def test_voice_config_relaxes_and_tightens() -> None:
    from comh.style_lint import VoiceConfig, validate_style

    text = "机制成立——数据稳定"
    punchy = VoiceConfig({"style": "punchy"})
    assert not punchy.enforces("em-dash")  # relaxed away
    plain = VoiceConfig(None)
    assert plain.enforces("em-dash")
    assert not any(f.check == "style:em-dash" for f in lint_text("P1", "title", text, punchy))
    assert any(f.check == "style:em-dash" for f in lint_text("P1", "title", text, plain))

    custom = VoiceConfig(
        {
            "style": "custom-voice",
            "rules": {"relax": ["em-dash"], "extra_metaphor_markers": ["内卷"]},
        }
    )
    assert not custom.enforces("em-dash")
    hits = lint_text("P2", "support_points[0]", "这个方案很内卷", custom)
    assert any(f.check == "style:metaphor" and "内卷" in f.detail for f in hits)

    # validate_style reads brief.voice end to end
    artifacts = {
        "brief": {"voice": {"style": "punchy"}},
        "deck_plan": {
            "deck": {
                "title": "t",
                "pages": [
                    {
                        "id": "P01",
                        "page_role": "content",
                        "title": "机制成立——数据稳定",
                        "support_points": ["要点"],
                    },
                ],
            }
        },
    }
    assert validate_style(artifacts, None) == []

    artifacts["brief"] = {"voice": {"rules": {"extra_forbidden": ["赋能"]}}}
    artifacts["deck_plan"]["deck"]["pages"][0]["support_points"] = ["全面赋能业务"]
    findings = validate_style(artifacts, None)
    assert any(f.check == "style:forbidden-word" and "赋能" in f.detail for f in findings)


def test_voice_is_per_medium() -> None:
    from comh.style_lint import validate_style

    # deck relaxed to punchy, report stays plain: same sentence, one surface flagged
    artifacts = {
        "brief": {"voice": {"deck": {"style": "punchy"}}},
        "deck_plan": {
            "deck": {
                "title": "t",
                "pages": [
                    {
                        "id": "P01",
                        "page_role": "content",
                        "title": "机制成立——数据稳定",
                        "support_points": ["要点"],
                    },
                ],
            }
        },
    }
    report = "机制成立——数据稳定；结论可用——先行灰度。"
    findings = validate_style(artifacts, report)
    assert not any(f.check == "style:em-dash" and f.artifact == "deck_plan" for f in findings), (
        "deck surface uses the punchy profile"
    )
    assert any(f.check == "style:em-dash" and f.artifact == "report_md" for f in findings), (
        "report surface keeps the plain profile"
    )

    # medium rules merge additively over the global rules
    artifacts["brief"] = {
        "voice": {
            "rules": {"extra_forbidden": ["赋能"]},
            "report": {"rules": {"extra_forbidden": ["综上所述"]}},
        }
    }
    artifacts["deck_plan"]["deck"]["pages"][0]["support_points"] = ["全面赋能业务"]
    report = "综上所述，方案可行。"
    findings = validate_style(artifacts, report)
    assert any(
        f.check == "style:forbidden-word" and "赋能" in f.detail and f.artifact == "deck_plan"
        for f in findings
    ), "global rules apply to deck"
    assert any(
        f.check == "style:forbidden-word" and "综上所述" in f.detail and f.artifact == "report_md"
        for f in findings
    ), "medium-specific rules apply to report"

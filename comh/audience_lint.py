"""Catch production-language leakage; semantic audience suitability still needs review."""

from __future__ import annotations

import re

from .artifacts import Finding
from .visible_text import page_texts, report_texts

# Match specific author-facing constructions, not words like 客户, 结论 or 适用边界.
RULES = (
    (
        "audience:planning-leak",
        "error",
        re.compile(
            r"(?:委托方|甲方|客户|受众|观众|听众)(?:最终|最|真正)?(?:关心|在意|想看到|想听)的(?:价值|内容|重点|结论)"
            r"|本页(?:的)?(?:目的|作用|任务|意图)[：:]?\s*(?:是)?(?:让|帮助|引导)(?:受众|观众|甲方|客户)"
            r"|(?:这[页张]|本页)(?:用来|用于|负责)(?:说服|打动|取悦)(?:甲方|客户|受众)"
        ),
        "Internal audience/production rationale leaked into visible copy; "
        "state the actual result or remove the label.",
    ),
    (
        "audience:empty-framing",
        "error",
        re.compile(
            r"先立住工具[，,]?\s*结论才有意义"
            r"|(?:机制层结论|应用层结论)[：:][^。；\n]*研究的直接产出[。]?\s*$"
        ),
        "Replace the abstract label with what was tested, observed or concluded; "
        "do not fill space with framing.",
    ),
    (
        "audience:compressed-boundary",
        "warn",
        re.compile(r"(?:适用边界|适用范围|模型边界)[：:][^\n。]*[·•][^\n。]*[·•][^\n。]*[·•]"),
        "Explain the model/conditions and what they prevent the audience from concluding; "
        "retain the real limitations.",
    ),
    (
        "audience:abstract-assurance",
        "warn",
        re.compile(r"确定性自洽|语义验证通过|可信性收口|证据链闭合"),
        "Explain the concrete verification and its limits; "
        "reproducibility alone does not establish real-world accuracy.",
    ),
    (
        "copy:encoded-entity",
        "error",
        re.compile(r"&(?:#x[0-9a-fA-F]+|#[0-9]+|nbsp|amp|lt|gt|quot);"),
        "A literal encoded entity reached visible copy; decode/remove it in the owning source.",
    ),
)


def lint_surface(artifact: str, location: str, text: str, brief: dict) -> list[Finding]:
    exceptions = (brief.get("audience") or {}).get("copy_exceptions") or []
    findings = []
    for rule, severity, pattern, advice in RULES:
        if not pattern.search(text):
            continue
        exception = next(
            (
                e
                for e in exceptions
                if e.get("rule") == rule
                and e.get("text") == text
                and e.get("location") == location
                and e.get("artifact") == artifact
                and e.get("reason", "").strip()
                and e.get("source", "").strip()
            ),
            None,
        )
        findings.append(
            Finding(
                artifact,
                rule,
                "info" if exception else severity,
                "pass" if exception else "fail",
                f"{location}: {advice} [{text[:100]}]"
                + (
                    f" Explicit exception: {exception['reason']} ({exception['source']})"
                    if exception
                    else ""
                ),
                artifact,
            )
        )
    return findings


def validate_audience_copy(artifacts: dict, report: str | None) -> list[Finding]:
    brief = artifacts.get("brief") or {}
    findings = []
    narrative = artifacts.get("narrative") or {}
    for collection, field in (("story", "message"), ("claims", "statement")):
        for entry in narrative.get(collection) or []:
            findings += lint_surface(
                "narrative", f"{entry['id']} {field}", str(entry.get(field, "")), brief
            )
    deck = (artifacts.get("deck_plan") or {}).get("deck") or {}
    findings += lint_surface("deck_plan", "deck.title", str(deck.get("title", "")), brief)
    for page in deck.get("pages") or []:
        seen = {}
        for element, text in page_texts(page):
            location = f"{page['id']} {element}"
            findings += lint_surface("deck_plan", location, text, brief)
            normalized = re.sub(r"\s", "", text)
            if len(normalized) >= 16 and normalized in seen:
                findings.append(
                    Finding(
                        "deck_plan",
                        "copy:duplicate",
                        "warn",
                        "fail",
                        f"{location}: repeats {seen[normalized]}; "
                        "check whether it adds information.",
                        "deck_plan",
                    )
                )
            seen[normalized] = location
    for location, text in report_texts(report or ""):
        findings += lint_surface("report_md", location, text, brief)
    return findings

"""Shared, deterministic communication contracts (no model judgment)."""

from __future__ import annotations

import re

COMMON_ARTIFACTS = {"evidence", "brief", "narrative"}
OUTPUT_ARTIFACT = {"deck": "deck_plan", "deck_html": "deck_plan", "report_docx": "report_md"}
MEDIA_OUTPUTS = {
    ("pptx", "presentation"): {"deck"},
    ("html", "presentation"): {"deck_html"},
    ("html", "data_story"): {"deck_html"},
    ("markdown", "report"): {"report_md"},
    ("docx", "report"): {"report_md", "report_docx"},
}


def requested_outputs(brief: dict) -> set[str]:
    return set().union(
        *(
            MEDIA_OUTPUTS.get((m.get("medium"), m.get("surface")), set())
            for m in brief.get("media", [])
        )
    )


def required_artifacts(brief: dict) -> set[str]:
    keys = set(COMMON_ARTIFACTS)
    outputs = requested_outputs(brief)
    if outputs & {"deck", "deck_html"}:
        keys.add("deck_plan")
    if outputs & {"report_md", "report_docx"}:
        keys.update(("report_plan", "report_md"))
    return keys


def hard_constraints(brief: dict) -> list[dict]:
    """Normalize legacy text without weakening unknown hard requirements."""
    result = []
    for index, raw in enumerate(brief.get("constraints", {}).get("hard", [])):
        if isinstance(raw, dict):
            result.append({"scope": "all", **raw})
            continue
        text = str(raw).strip()
        rule = {"id": f"hard-{index + 1}", "text": text, "scope": "all", "check": "manual"}
        for pattern, check in (
            (r"必须包含[:：]?\s*(.+)", "contains"),
            (r"(?:不得出现|不得写|禁止出现|禁止写)[:：]?\s*(.+)", "forbidden"),
        ):
            match = re.search(pattern, text)
            if match:
                rule.update(check=check, value=match.group(1).strip().strip("'\"“”‘’「」"))
                # The documented legacy contains rule targets the report when
                # one is requested. Structured rules make scope explicit.
                if check == "contains" and requested_outputs(brief) & {"report_md", "report_docx"}:
                    rule["scope"] = "report"
                break
        if re.search(
            r"(?:不要|禁止|不得|不能).*?(?:黑底|暗色背景|深色背景)|no dark background", text, re.I
        ):
            rule.update(check="light_background", scope="deck")
        result.append(rule)
    return result


def forbids_dark(brief: dict) -> bool:
    return any(c["check"] == "light_background" for c in hard_constraints(brief))


def page_beats(page: dict) -> list[str]:
    return list(dict.fromkeys(([page["beat"]] if page.get("beat") else []) + page.get("beats", [])))


def direct_evidence(node: dict) -> list[str]:
    """Only semantic evidence fields; do not interpret arbitrary extension text."""
    refs = list(node.get("evidence", [])) if isinstance(node.get("evidence"), list) else []
    visual = node.get("visual") or {}
    entries = [
        *(node.get("metric_cards") or []),
        *((visual.get("chart") or {}).get("series") or []),
        *(
            cell
            for row in (visual.get("table") or {}).get("rows", [])
            for cell in row
            if isinstance(cell, dict)
        ),
    ]
    refs += [entry["value_from"] for entry in entries if entry.get("value_from")]
    refs += [entry["evidence"] for entry in entries if entry.get("evidence")]
    for entry in [*(visual.get("asset_refs") or []), visual.get("diagram"), node.get("callout")]:
        if isinstance(entry, dict) and entry.get("evidence"):
            refs.append(entry["evidence"])
    return list(dict.fromkeys(refs))


def derived_operands(item: dict) -> list[str]:
    locator = str((item.get("source") or {}).get("locator", ""))
    match = re.fullmatch(r"derived:\(([^)]*)\)", locator.strip())
    return [s.strip() for s in match.group(1).split(",") if s.strip()] if match else []

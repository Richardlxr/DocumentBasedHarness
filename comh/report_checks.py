"""Map report headings to section contracts and check literal requirements."""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

from .artifacts import Finding

_CITATION = re.compile(r"\[(E\d{3,})\]")


def prose(text: str) -> str:
    """Visible prose, excluding code, comments and link/image destinations."""
    return "\n".join(
        "".join(
            child.content
            if child.type in {"text", "image"}
            else "\n"
            if child.type in {"softbreak", "hardbreak"}
            else ""
            for child in token.children or []
        )
        for token in MarkdownIt().parse(text)
        if token.type == "inline"
    )


def normalize_heading(text: str) -> str:
    return re.sub(r"^(?:[一二三四五六七八九十百]+[、.．]|\d+[、.．)]\s*)\s*", "", text).strip()


def section_bodies(plan: dict, text: str) -> dict[str, list[str]]:
    lines = text.splitlines()
    tokens = MarkdownIt().parse(text)
    headings = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            headings.append(
                (normalize_heading(tokens[index + 1].content), int(token.tag[1:]), token.map[0])
            )
    result = {}
    for section in plan.get("sections", []):
        matches = []
        for index, (heading, level, start) in enumerate(headings):
            if heading != normalize_heading(section["heading"]):
                continue
            end = next((s for _, lev, s in headings[index + 1 :] if lev <= level), len(lines))
            matches.append("\n".join(lines[start:end]))
        result[section["id"]] = matches
    return result


def validate_report(artifacts: dict, text: str | None) -> list[Finding]:
    if text is None:
        return []
    findings = []
    evidence_ids = {i["id"] for i in (artifacts.get("evidence") or {}).get("items", [])}
    for ref in sorted(set(_CITATION.findall(prose(text))) - evidence_ids):
        findings.append(
            Finding(
                "report_md",
                "ref-integrity",
                "error",
                "fail",
                f"report cites missing evidence '{ref}'",
            )
        )
    plan = artifacts.get("report_plan") or {}
    bodies = section_bodies(plan, text)
    for section in plan.get("sections", []):
        matches = bodies[section["id"]]
        if len(matches) != 1:
            findings.append(
                Finding(
                    "report_md",
                    "report-contract",
                    "error",
                    "fail",
                    f"section {section['id']} heading '{section['heading']}' "
                    f"must appear exactly once (found {len(matches)})",
                )
            )
            continue
        body = prose(matches[0])
        for phrase in section.get("must_include", []):
            if phrase not in body:
                findings.append(
                    Finding(
                        "report_md",
                        "report-contract",
                        "error",
                        "fail",
                        f"section {section['id']} must include literal text '{phrase}'",
                    )
                )
        cited = set(_CITATION.findall(body))
        for ref in set(section.get("evidence", [])) - cited:
            findings.append(
                Finding(
                    "report_md",
                    "report-contract",
                    "error",
                    "fail",
                    f"section {section['id']} must cite [{ref}] inline",
                )
            )
    return findings

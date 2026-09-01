"""Deterministic cross-artifact validators.

Every finding names its owning artifact so the repair loop knows which layer to
reopen. Judgment-based checks (logic, audience fit, titles) are model-side and
live in ``stages/qa.md``; only mechanically checkable invariants live here.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .artifacts import (
    KNOWN_CLAIM_STATUSES,
    KNOWN_PAGE_ROLES,
    Finding,
    load_artifact,
)
from .manifest import Manifest

# Numbers immediately followed by 年/月/日 are dates, not data. IDs (E001, P99,
# v2) are excluded by the lookbehind.
_NUMBER = re.compile(r"(?<![A-Za-z\d])-?\d+(?:\.\d+)?(?!\s*[年月日])")
# Code fences and MyST directive blocks are metadata/structure, not report prose.
_NON_PROSE = re.compile(r"```.*?```|^:::.*?:::", re.DOTALL | re.MULTILINE)
# Ordered-list markers ("1. ", "2、") are structure, not data.
_LIST_MARKER = re.compile(r"^(\s*)\d+[.、)]\s+", re.MULTILINE)
_MUST_INCLUDE = re.compile(r"必须包含[:：]?\s*(.+)")
_BACKGROUND_FORBIDS_DARK = re.compile(r"黑底|暗色背景|深色背景|dark background", re.IGNORECASE)


def _numbers_in(text: str) -> set[float]:
    return {round(float(token), 2) for token in _NUMBER.findall(text or "")}


def _evidence_number_pool(evidence: dict | None) -> set[float]:
    pool: set[float] = set()
    for item in (evidence or {}).get("items", []):
        value = item.get("value")
        if isinstance(value, dict) and isinstance(value.get("number"), (int, float)):
            pool.add(round(float(value["number"]), 2))
        pool |= _numbers_in(str(item.get("content", "")))
    return pool


def validate_refs(artifacts: dict[str, dict | None]) -> list[Finding]:
    """ID-chain integrity: every cross-artifact reference resolves."""
    findings: list[Finding] = []
    evidence_ids = {i["id"] for i in (artifacts.get("evidence") or {}).get("items", [])}
    narrative = artifacts.get("narrative") or {}
    claim_ids = {c["id"] for c in narrative.get("claims", [])}
    beat_ids = {b["id"] for b in narrative.get("story", [])}

    for claim in narrative.get("claims", []):
        for ref in claim.get("evidence", []):
            if ref not in evidence_ids:
                findings.append(
                    Finding(
                        "narrative", "ref-integrity", "error", "fail",
                        f"claim {claim['id']} references missing evidence '{ref}'", "evidence",
                    )
                )
    for beat in narrative.get("story", []):
        for ref in beat.get("claims", []):
            if ref not in claim_ids:
                findings.append(
                    Finding(
                        "narrative", "ref-integrity", "error", "fail",
                        f"beat {beat['id']} references missing claim '{ref}'", "narrative",
                    )
                )

    deck = artifacts.get("deck_plan") or {}
    for page in deck.get("deck", {}).get("pages", []):
        beat = page.get("beat")
        if beat and beat not in beat_ids:
            findings.append(
                Finding(
                    "deck_plan", "ref-integrity", "error", "fail",
                    f"page {page['id']} references missing beat '{beat}'", "narrative",
                )
            )
        if page.get("page_role") not in KNOWN_PAGE_ROLES:
            findings.append(
                Finding(
                    "deck_plan", "page-role", "warn", "pass",
                    f"page {page['id']} uses unknown page_role '{page.get('page_role')}' "
                    f"(treated as content)", "deck_plan",
                )
            )
        for item in (page.get("visual") or {}).get("asset_refs", []):
            if isinstance(item, dict) and item.get("evidence", "") not in evidence_ids:
                findings.append(
                    Finding(
                        "deck_plan", "ref-integrity", "error", "fail",
                        f"page {page['id']} figure '{item.get('ref')}' references missing "
                        f"evidence '{item.get('evidence')}'", "evidence",
                    )
                )

    report_plan = artifacts.get("report_plan") or {}
    for section in report_plan.get("sections", []):
        for ref in section.get("beats", []):
            if ref not in beat_ids:
                findings.append(
                    Finding(
                        "report_plan", "ref-integrity", "error", "fail",
                        f"section {section['id']} references missing beat '{ref}'", "narrative",
                    )
                )
        for ref in section.get("claims", []):
            if ref not in claim_ids:
                findings.append(
                    Finding(
                        "report_plan", "ref-integrity", "error", "fail",
                        f"section {section['id']} references missing claim '{ref}'", "narrative",
                    )
                )
        for ref in section.get("evidence", []):
            if ref not in evidence_ids:
                findings.append(
                    Finding(
                        "report_plan", "ref-integrity", "error", "fail",
                        f"section {section['id']} references missing evidence '{ref}'", "evidence",
                    )
                )
    return findings


def validate_claims(artifacts: dict[str, dict | None]) -> list[Finding]:
    """Grounding honesty: supported claims must cite evidence; statuses must be known;
    claims resting solely on visual estimates are flagged (chart reads are
    estimates, not ground truth)."""
    findings: list[Finding] = []
    narrative = artifacts.get("narrative") or {}
    evidence_items = {i["id"]: i for i in (artifacts.get("evidence") or {}).get("items", [])}
    for claim in narrative.get("claims", []):
        status = claim.get("status")
        if status not in KNOWN_CLAIM_STATUSES:
            findings.append(
                Finding(
                    "narrative", "claim-status", "warn", "pass",
                    f"claim {claim['id']} has unknown status '{status}' (treated as needs review)",
                    "narrative",
                )
            )
        if status == "supported" and not claim.get("evidence"):
            findings.append(
                Finding(
                    "narrative", "claims-grounded", "error", "fail",
                    f"claim {claim['id']} is 'supported' but cites no evidence; "
                    f"demote to background/assumption or add evidence", "narrative",
                )
            )
        refs = claim.get("evidence", [])
        cited = [evidence_items[r] for r in refs if r in evidence_items]
        estimated_only = (
            status == "supported"
            and cited
            and all(
                (item.get("extraction") or {}).get("confidence") == "estimated"
                for item in cited
            )
        )
        if estimated_only:
            findings.append(
                Finding(
                    "narrative", "visual-estimate-only", "warn", "fail",
                    f"claim {claim['id']} rests only on visually estimated evidence "
                    f"({', '.join(refs)}); verify against an underlying data file "
                    f"or soften the claim", "evidence",
                )
            )
    return findings


def validate_numbers(
    artifacts: dict[str, dict | None], report_md_text: str | None
) -> list[Finding]:
    """Number consistency: numbers downstream must exist in the evidence store.

    Claims are error-level (claim statements are supposed to be grounded);
    deck/report prose is warn-level (rounding and phrasing differences are
    legitimate but should be visible).
    """
    findings: list[Finding] = []
    pool = _evidence_number_pool(artifacts.get("evidence"))
    narrative = artifacts.get("narrative") or {}
    for claim in narrative.get("claims", []):
        for number in sorted(_numbers_in(claim.get("statement", ""))):
            if number not in pool:
                findings.append(
                    Finding(
                        "narrative", "number-consistency", "error", "fail",
                        f"claim {claim['id']} uses number {number:g} that appears in no evidence "
                        f"item; materialize it as a datum first", "evidence",
                    )
                )
    deck = artifacts.get("deck_plan") or {}
    for page in deck.get("deck", {}).get("pages", []):
        parts = [page.get("title", "")]
        for entry in page.get("support_points", []):
            if isinstance(entry, dict):
                parts.append(str(entry.get("point", "")))
                parts.append(str(entry.get("detail", "") or ""))
            else:
                parts.append(str(entry))
        if page.get("callout"):
            parts.append(str(page["callout"].get("text", "")))
        text = " ".join(parts)
        for number in sorted(_numbers_in(text)):
            if number not in pool:
                findings.append(
                    Finding(
                        "deck_plan", "number-consistency", "warn", "fail",
                        f"page {page['id']} uses number {number:g} not found in evidence "
                        f"(check rounding or add a derived datum)", "deck_plan",
                    )
                )
    if report_md_text:
        prose = _LIST_MARKER.sub(r"\1", _NON_PROSE.sub("", report_md_text))
        for number in sorted(_numbers_in(prose)):
            if number not in pool:
                findings.append(
                    Finding(
                        "report_md", "number-consistency", "warn", "fail",
                        f"report uses number {number:g} not found in evidence", "report_md",
                    )
                )
    return findings


def validate_coverage(artifacts: dict[str, dict | None]) -> list[Finding]:
    """Beats confirmed at Gate 2 must not silently vanish from projections."""
    findings: list[Finding] = []
    narrative = artifacts.get("narrative") or {}
    beat_ids = {b["id"] for b in narrative.get("story", [])}
    covered: set[str] = set()
    deck = artifacts.get("deck_plan") or {}
    covered |= {p["beat"] for p in deck.get("deck", {}).get("pages", []) if p.get("beat")}
    report_plan = artifacts.get("report_plan") or {}
    for section in report_plan.get("sections", []):
        covered |= set(section.get("beats", []))
    for beat_id in sorted(beat_ids - covered):
        findings.append(
            Finding(
                "narrative", "beat-coverage", "warn", "fail",
                f"beat {beat_id} is not covered by any deck page or report section; "
                f"if intentional, say so via a demotion or appendix", "deck_plan",
            )
        )
    return findings


def validate_visuals(artifacts: dict[str, dict | None]) -> list[Finding]:
    """Cards and charts may only plot structured evidence: value_from must resolve
    to an item carrying value.number. Values are pulled at render time, so card
    and chart numbers cannot drift — this check only guarantees the references
    are real. Callout evidence links resolve too."""
    findings: list[Finding] = []
    deck = artifacts.get("deck_plan") or {}
    evidence_items = {i["id"]: i for i in (artifacts.get("evidence") or {}).get("items", [])}

    def check_value_ref(page_id: str, ref: str, what: str) -> None:
        item = evidence_items.get(ref)
        if item is None:
            findings.append(
                Finding(
                    "deck_plan", "ref-integrity", "error", "fail",
                    f"page {page_id} {what} references missing evidence '{ref}'", "evidence",
                )
            )
        elif (item.get("value") or {}).get("number") is None:
            findings.append(
                Finding(
                    "deck_plan", "visual", "error", "fail",
                    f"page {page_id} {what}: evidence '{ref}' has no value.number; "
                    f"cards and charts plot structured data only", "evidence",
                )
            )

    for page in deck.get("deck", {}).get("pages", []):
        page_id = page["id"]
        # Known visual subkeys placed at page level are a silent footgun in an
        # open schema: the renderer would never see them. Surface the typo.
        for stray in ("chart", "diagram", "asset_refs"):
            if stray in page:
                findings.append(
                    Finding(
                        "deck_plan", "schema", "warn", "fail",
                        f"page {page_id} has '{stray}' at page level; it belongs under "
                        f"'visual' and the renderer ignores misplaced keys", "deck_plan",
                    )
                )
        chart = (page.get("visual") or {}).get("chart")
        if chart:
            for entry in chart.get("series", []):
                check_value_ref(page_id, str(entry.get("value_from", "")), "chart series")
        for card in page.get("metric_cards") or []:
            check_value_ref(page_id, str(card.get("value_from", "")), "metric card")
        diagram = (page.get("visual") or {}).get("diagram")
        if diagram:
            if diagram.get("evidence") and diagram["evidence"] not in evidence_items:
                findings.append(
                    Finding(
                        "deck_plan", "ref-integrity", "error", "fail",
                        f"page {page_id} diagram references missing evidence "
                        f"'{diagram['evidence']}'", "evidence",
                    )
                )
            # Dry-run mermaid → DrawioDocument (pure Python, no draw.io CLI) so
            # bad diagram syntax fails at validation, not at render time.
            from .render.diagrams import dry_convert

            error = dry_convert(str(diagram.get("mermaid", "")))
            if error:
                findings.append(
                    Finding(
                        "deck_plan", "diagram", "error", "fail",
                        f"page {page_id} diagram does not compile: {error}", "deck_plan",
                    )
                )
        callout = page.get("callout")
        if callout and callout.get("evidence") and callout["evidence"] not in evidence_items:
            findings.append(
                Finding(
                    "deck_plan", "ref-integrity", "error", "fail",
                    f"page {page_id} callout references missing evidence "
                    f"'{callout['evidence']}'", "evidence",
                )
            )
    return findings


def validate_hard_constraints(
    artifacts: dict[str, dict | None], report_md_text: str | None
) -> list[Finding]:
    """Deterministic enforcement of the brief's hard constraints (pattern registry)."""
    findings: list[Finding] = []
    brief = artifacts.get("brief") or {}
    hard = brief.get("constraints", {}).get("hard", [])
    report_plan = artifacts.get("report_plan") or {}

    for constraint in hard:
        if _BACKGROUND_FORBIDS_DARK.search(constraint):
            from .render.theme import select_theme

            style = (artifacts.get("deck_plan") or {}).get("deck", {}).get("style")
            choice = select_theme(style, allow_dark=False)
            if choice.forced_light:
                findings.append(
                    Finding(
                        "brief", "hard-constraint", "error", "fail",
                        f"constraint '{constraint}' but deck.style.template "
                        f"'{choice.requested}' is dark; pick a light template "
                        f"(renderer would force light anyway)", "deck_plan",
                    )
                )
            else:
                findings.append(
                    Finding(
                        "brief", "hard-constraint", "info", "pass",
                        f"constraint '{constraint}' enforced: light theme "
                        f"'{choice.theme.name}' selected", "deck_plan",
                    )
                )
        match = _MUST_INCLUDE.search(constraint)
        if match:
            phrase = match.group(1).strip()
            haystacks = [report_md_text or ""]
            sections = report_plan.get("sections", [])
            haystacks += [s.get("heading", "") for s in sections]
            haystacks += [m for s in sections for m in s.get("must_include", [])]
            if not any(phrase in h for h in haystacks):
                findings.append(
                    Finding(
                        "brief", "hard-constraint", "error", "fail",
                        f"constraint requires '{phrase}' but it appears in no report section "
                        f"heading/must_include", "report_plan",
                    )
                )
    return findings


def run_all(run_root: Path) -> list[Finding]:
    manifest = Manifest.load(run_root)
    artifacts: dict[str, dict | None] = {}
    findings: list[Finding] = []
    for key in ("evidence", "brief", "narrative", "deck_plan", "report_plan"):
        data, schema_findings = load_artifact(run_root, key)
        artifacts[key] = data
        findings += schema_findings

    report_path = run_root / manifest.data["artifacts"]["report_md"]["path"]
    report_md_text = report_path.read_text(encoding="utf-8") if report_path.is_file() else None

    if all(artifacts.get(k) is not None for k in ("evidence", "narrative")):
        findings += validate_refs(artifacts)
        findings += validate_claims(artifacts)
        findings += validate_numbers(artifacts, report_md_text)
        findings += validate_coverage(artifacts)
        findings += validate_visuals(artifacts)
    if artifacts.get("brief") is not None:
        findings += validate_hard_constraints(artifacts, report_md_text)

    for gate, record in manifest.data["gates"].items():
        if record.get("confirmed") and not manifest.gate_valid(gate):
            findings.append(
                Finding(
                    gate, "gate", "warn", "fail",
                    f"gate '{gate}' confirmed at {record.get('at')} but the file changed since",
                    gate,
                )
            )
    return findings


def write_findings(run_root: Path, findings: list[Finding]) -> Path:
    qa_dir = run_root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    path = qa_dir / "findings.yaml"
    payload = {
        "count": {"error": 0, "warn": 0, "info": 0},
        "findings": [f.as_dict() for f in findings],
    }
    for f in findings:
        payload["count"][f.severity] += 1
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


__all__ = [
    "run_all",
    "write_findings",
    "validate_visuals",
    "validate_claims",
    "validate_coverage",
    "validate_hard_constraints",
    "validate_numbers",
    "validate_refs",
]

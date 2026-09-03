"""Deterministic cross-artifact validators.

Every finding names its owning artifact so the repair loop knows which layer to
reopen. Judgment-based checks (logic, audience fit, titles) are model-side and
live in ``stages/qa.md``; only mechanically checkable invariants live here.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import yaml

from .artifacts import (
    KNOWN_CLAIM_STATUSES,
    KNOWN_PAGE_ROLES,
    Finding,
    load_artifact,
)
from .contracts import (
    MEDIA_OUTPUTS,
    derived_operands,
    direct_evidence,
    hard_constraints,
    page_beats,
    required_artifacts,
)
from .manifest import Manifest
from .report_checks import prose, validate_report

# Numbers immediately followed by 年/月/日 are dates, not data. IDs (E001, P99,
# v2) are excluded by the lookbehind.
_NUMBER = re.compile(r"(?<![A-Za-z\d])-?\d+(?:\.\d+)?(?![\d.]|\s*[年月日])")
# Code fences and MyST directive blocks are metadata/structure, not report prose.
_NON_PROSE = re.compile(r"```.*?```|^:::.*?:::", re.DOTALL | re.MULTILINE)
# Ordered-list markers ("1. ", "2、") are structure, not data.
_LIST_MARKER = re.compile(r"^(\s*)\d+[.、)]\s+", re.MULTILINE)

# Reveal/emphasis semantics (fragment model): element addresses resolve against
# the page structure deterministically at validation time.
_ADDRESS = re.compile(r"^([a-z_]+)(?:\[(\d+)\])?$")
_ELEMENT_BASES = {"title", "callout", "visual", "support_points", "metric_cards"}
_KNOWN_VERBS = {"appear", "fade_in", "emphasize", "highlight"}
_KNOWN_TRIGGERS = {"click", "with_previous", "after"}


def _iter_strings(node) -> list[str]:
    """All string values nested in a JSON-ish structure (deck titles, labels, notes…)."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for v in node.values() for s in _iter_strings(v)]
    if isinstance(node, (list, tuple)):
        return [s for v in node for s in _iter_strings(v)]
    return []


def _numbers_in(text: str) -> set[Decimal]:
    return {Decimal(token) for token in _NUMBER.findall(text or "")}


def _evidence_number_pool(evidence: dict | None) -> set[Decimal]:
    pool: set[Decimal] = set()
    for item in (evidence or {}).get("items", []):
        value = item.get("value")
        if isinstance(value, dict) and isinstance(value.get("number"), (int, float)):
            pool.add(Decimal(str(value["number"])))
        pool |= _numbers_in(str(item.get("content", "")))
    return pool


def validate_sources(artifacts: dict[str, dict | None], run_root: Path) -> list[Finding]:
    """Source resolution, workspace containment and an acyclic derivation graph."""
    from .derivations import calculate

    findings = []
    evidence = artifacts.get("evidence") or {}
    items = {i["id"]: i for i in evidence.get("items", [])}
    registry = {e["id"]: e for e in evidence.get("sources", [])}
    graph = {key: derived_operands(item) for key, item in items.items()}

    def error(detail, check="ref-integrity"):
        findings.append(Finding("evidence", check, "error", "fail", detail))

    for source_id, entry in registry.items():
        raw = Path(entry["path"])
        path = (run_root / raw).resolve()
        if raw.is_absolute() or not path.is_relative_to(run_root.resolve() / "sources"):
            error(f"source '{source_id}' must stay under sources/: {raw}")
        elif not path.is_file():
            users = ", ".join(
                key
                for key, item in items.items()
                if item.get("source", {}).get("source") == source_id
            )
            error(f"source '{source_id}' path '{raw}' does not exist (evidence: {users})")

    for item_id, item in items.items():
        source = item.get("source") or {}
        ref, locator = source.get("source", ""), source.get("locator", "")
        if not str(locator).strip():
            error(f"evidence {item_id} needs a non-empty source locator")
        if ref != "derived" and ref not in registry:
            error(
                f"evidence {item_id} cites source '{ref}' which is not in the sources registry",
                "source-registry" if not registry else "ref-integrity",
            )
        if ref != "derived" and "derived:" not in str(locator):
            continue
        operands = graph[item_id]
        if not operands:
            error(
                f"evidence {item_id} has a derived locator with no operands "
                "(expected 'derived:(E001,E002)')"
            )
        for operand in operands:
            if operand not in items:
                error(f"evidence {item_id} derived locator references missing evidence '{operand}'")
        calculation = item.get("derived") or {}
        if not calculation.get("formula"):
            findings.append(
                Finding(
                    "evidence",
                    "derived-calculation",
                    "warn",
                    "fail",
                    f"evidence {item_id}: no derived.formula; arithmetic has not been verified",
                )
            )
        else:
            try:
                result = calculate(
                    calculation["formula"], {op: items[op]["value"]["number"] for op in operands}
                )
                precision = calculation.get("precision", 2)
                actual = item["value"]["number"]
                if round(result, precision) != round(actual, precision):
                    error(
                        f"evidence {item_id}: formula gives {result:g}, "
                        f"recorded value is {actual:g}",
                        "derived-calculation",
                    )
            except (ValueError, SyntaxError, TypeError, KeyError, ArithmeticError) as exc:
                error(
                    f"evidence {item_id}: invalid derived calculation: {exc}", "derived-calculation"
                )

    active, done = set(), set()

    def visit(key):
        if key in active:
            error(f"derived evidence cycle reaches '{key}'")
            return
        if key in done:
            return
        active.add(key)
        for op in graph.get(key, []):
            if op in items:
                visit(op)
        active.remove(key)
        done.add(key)

    for key in items:
        visit(key)
    return findings


def validate_refs(artifacts: dict[str, dict | None]) -> list[Finding]:
    """ID-chain integrity: every cross-artifact reference resolves."""
    findings: list[Finding] = []
    evidence_ids = {i["id"] for i in (artifacts.get("evidence") or {}).get("items", [])}
    narrative = artifacts.get("narrative") or {}
    claim_ids = {c["id"] for c in narrative.get("claims", [])}
    beat_ids = {b["id"] for b in narrative.get("story", [])}

    for claim in narrative.get("claims", []):
        for ref in claim.get("evidence", []) + claim.get("counterevidence", []):
            if ref not in evidence_ids:
                findings.append(
                    Finding(
                        "narrative",
                        "ref-integrity",
                        "error",
                        "fail",
                        f"claim {claim['id']} references missing evidence '{ref}'",
                        "evidence",
                    )
                )
    for beat in narrative.get("story", []):
        for ref in beat.get("claims", []):
            if ref not in claim_ids:
                findings.append(
                    Finding(
                        "narrative",
                        "ref-integrity",
                        "error",
                        "fail",
                        f"beat {beat['id']} references missing claim '{ref}'",
                        "narrative",
                    )
                )

    deck = artifacts.get("deck_plan") or {}
    for page in deck.get("deck", {}).get("pages", []):
        beat = page.get("beat")
        if page.get("page_role") not in {
            "cover",
            "agenda",
            "section_divider",
            "closing",
            "appendix",
        } and not page_beats(page):
            findings.append(
                Finding(
                    "deck_plan",
                    "ref-integrity",
                    "error",
                    "fail",
                    f"content page {page['id']} must reference a story beat",
                )
            )
        for ref in page_beats(page):
            if ref != beat and ref not in beat_ids:
                findings.append(
                    Finding(
                        "deck_plan",
                        "ref-integrity",
                        "error",
                        "fail",
                        f"page {page['id']} references missing beat '{ref}'",
                    )
                )
        if len(page_beats(page)) > 1 and not page.get("merge_rationale", "").strip():
            findings.append(
                Finding(
                    "deck_plan",
                    "ref-integrity",
                    "error",
                    "fail",
                    f"page {page['id']} merges beats without merge_rationale",
                )
            )
        for ref in direct_evidence(page):
            if ref not in evidence_ids:
                findings.append(
                    Finding(
                        "deck_plan",
                        "ref-integrity",
                        "error",
                        "fail",
                        f"page {page['id']} references missing evidence '{ref}'",
                    )
                )
        if beat and beat not in beat_ids:
            findings.append(
                Finding(
                    "deck_plan",
                    "ref-integrity",
                    "error",
                    "fail",
                    f"page {page['id']} references missing beat '{beat}'",
                    "narrative",
                )
            )
        if page.get("page_role") not in KNOWN_PAGE_ROLES:
            findings.append(
                Finding(
                    "deck_plan",
                    "page-role",
                    "warn",
                    "pass",
                    f"page {page['id']} uses unknown page_role '{page.get('page_role')}' "
                    f"(treated as content)",
                    "deck_plan",
                )
            )
        for item in (page.get("visual") or {}).get("asset_refs", []):
            if isinstance(item, dict) and item.get("evidence", "") not in evidence_ids:
                findings.append(
                    Finding(
                        "deck_plan",
                        "ref-integrity",
                        "error",
                        "fail",
                        f"page {page['id']} figure '{item.get('ref')}' references missing "
                        f"evidence '{item.get('evidence')}'",
                        "evidence",
                    )
                )

    report_plan = artifacts.get("report_plan") or {}
    for section in report_plan.get("sections", []):
        if len(section.get("beats", [])) > 1 and not section.get("merge_rationale", "").strip():
            findings.append(
                Finding(
                    "report_plan",
                    "ref-integrity",
                    "error",
                    "fail",
                    f"section {section['id']} merges beats without merge_rationale",
                )
            )
        for ref in section.get("beats", []):
            if ref not in beat_ids:
                findings.append(
                    Finding(
                        "report_plan",
                        "ref-integrity",
                        "error",
                        "fail",
                        f"section {section['id']} references missing beat '{ref}'",
                        "narrative",
                    )
                )
        for ref in section.get("claims", []):
            if ref not in claim_ids:
                findings.append(
                    Finding(
                        "report_plan",
                        "ref-integrity",
                        "error",
                        "fail",
                        f"section {section['id']} references missing claim '{ref}'",
                        "narrative",
                    )
                )
        for ref in section.get("evidence", []):
            if ref not in evidence_ids:
                findings.append(
                    Finding(
                        "report_plan",
                        "ref-integrity",
                        "error",
                        "fail",
                        f"section {section['id']} references missing evidence '{ref}'",
                        "evidence",
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
                    "narrative",
                    "claim-status",
                    "warn",
                    "pass",
                    f"claim {claim['id']} has unknown status '{status}' (treated as needs review)",
                    "narrative",
                )
            )
        if status == "supported" and not claim.get("evidence"):
            findings.append(
                Finding(
                    "narrative",
                    "claims-grounded",
                    "error",
                    "fail",
                    f"claim {claim['id']} is 'supported' but cites no evidence; "
                    f"demote to background/assumption or add evidence",
                    "narrative",
                )
            )
        refs = claim.get("evidence", [])
        cited = [evidence_items[r] for r in refs if r in evidence_items]
        estimated_only = (
            status == "supported"
            and cited
            and all(
                (item.get("extraction") or {}).get("confidence") == "estimated" for item in cited
            )
        )
        if estimated_only:
            findings.append(
                Finding(
                    "narrative",
                    "visual-estimate-only",
                    "warn",
                    "fail",
                    f"claim {claim['id']} rests only on visually estimated evidence "
                    f"({', '.join(refs)}); verify against an underlying data file "
                    f"or soften the claim",
                    "evidence",
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
    evidence_items = {i["id"]: i for i in (artifacts.get("evidence") or {}).get("items", [])}
    for claim in narrative.get("claims", []):
        cited = [evidence_items[ref] for ref in claim.get("evidence", []) if ref in evidence_items]
        claim_pool = _evidence_number_pool({"items": cited})
        for number in sorted(_numbers_in(claim.get("statement", ""))):
            if number not in claim_pool:
                findings.append(
                    Finding(
                        "narrative",
                        "number-consistency",
                        "error",
                        "fail",
                        f"claim {claim['id']}: number {number:g} absent from its cited evidence "
                        f"items; cite the matching datum or materialize it first",
                        "evidence",
                    )
                )
        units = {str((i.get("value") or {}).get("unit", "")) for i in cited} - {""}
        unit_pattern = "|".join(
            re.escape(u)
            for u in sorted(
                units | {"ms", "us", "ns", "ps", "s", "GB", "MB", "KB", "QPS", "%"},
                key=len,
                reverse=True,
            )
        )
        quantity = re.compile(rf"(?<![A-Za-z\d])(-?\d+(?:\.\d+)?)\s*({unit_pattern})(?![A-Za-z])")
        supported = {
            (Decimal(m[1]), m[2]) for i in cited for m in quantity.finditer(i.get("content", ""))
        }
        for item in cited:
            value = item.get("value") or {}
            if value.get("number") is not None and value.get("unit"):
                supported.add((Decimal(str(value["number"])), value["unit"]))
        if units:
            for match in quantity.finditer(claim.get("statement", "")):
                token = re.sub(r"\s+", "", match.group())
                if (Decimal(match[1]), match[2]) not in supported:
                    findings.append(
                        Finding(
                            "narrative",
                            "quantity-consistency",
                            "error",
                            "fail",
                            f"claim {claim['id']}: quantity '{token}' absent from cited evidence",
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
                        "deck_plan",
                        "number-consistency",
                        "warn",
                        "fail",
                        f"page {page['id']} uses number {number:g} not found in evidence "
                        f"(check rounding or add a derived datum)",
                        "deck_plan",
                    )
                )
    if report_md_text:
        prose = _LIST_MARKER.sub(r"\1", _NON_PROSE.sub("", report_md_text))
        for number in sorted(_numbers_in(prose)):
            if number not in pool:
                findings.append(
                    Finding(
                        "report_md",
                        "number-consistency",
                        "warn",
                        "fail",
                        f"report uses number {number:g} not found in evidence",
                        "report_md",
                    )
                )
    return findings


def validate_coverage(artifacts: dict[str, dict | None]) -> list[Finding]:
    """Every projection accounts for its own beats and intentional omissions."""
    findings = []
    beat_ids = {b["id"] for b in (artifacts.get("narrative") or {}).get("story", [])}
    for key in ("deck_plan", "report_plan"):
        plan = artifacts.get(key)
        if plan is None:
            continue
        covered = set()
        if key == "deck_plan":
            for page in plan.get("deck", {}).get("pages", []):
                covered.update(page_beats(page))
        else:
            for section in plan.get("sections", []):
                covered.update(section.get("beats", []))
        omissions = plan.get("omissions", [])
        omitted = set()
        for omission in omissions:
            beat = omission["beat"]
            if beat not in beat_ids or not omission.get("reason", "").strip():
                findings.append(
                    Finding(
                        key,
                        "beat-coverage",
                        "error",
                        "fail",
                        f"invalid omission for beat '{beat}': a real beat and reason are required",
                    )
                )
            else:
                omitted.add(beat)
                findings.append(
                    Finding(
                        key,
                        "beat-coverage",
                        "info",
                        "pass",
                        f"beat {beat} omitted from {key}: {omission['reason']}",
                    )
                )
        for beat in sorted(beat_ids - covered - omitted):
            findings.append(
                Finding(
                    key,
                    "beat-coverage",
                    "warn",
                    "fail",
                    f"beat {beat} is not covered by {key}; "
                    "add it or record a reason in this projection's omissions",
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
                    "deck_plan",
                    "ref-integrity",
                    "error",
                    "fail",
                    f"page {page_id} {what} references missing evidence '{ref}'",
                    "evidence",
                )
            )
        elif (item.get("value") or {}).get("number") is None:
            findings.append(
                Finding(
                    "deck_plan",
                    "visual",
                    "error",
                    "fail",
                    f"page {page_id} {what}: evidence '{ref}' has no value.number; "
                    f"cards and charts plot structured data only",
                    "evidence",
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
                        "deck_plan",
                        "schema",
                        "warn",
                        "fail",
                        f"page {page_id} has '{stray}' at page level; it belongs under "
                        f"'visual' and the renderer ignores misplaced keys",
                        "deck_plan",
                    )
                )
        chart = (page.get("visual") or {}).get("chart")
        if chart:
            for entry in chart.get("series", []):
                check_value_ref(page_id, str(entry.get("value_from", "")), "chart series")
        for card in page.get("metric_cards") or []:
            check_value_ref(page_id, str(card.get("value_from", "")), "metric card")
        from .render.icons import icon_exists

        for icon_source in [page.get("metric_cards") or []] + [page.get("support_points") or []]:
            for entry in icon_source:
                icon_name = str(entry.get("icon") or "") if isinstance(entry, dict) else ""
                if icon_name and not icon_exists(icon_name):
                    findings.append(
                        Finding(
                            "deck_plan",
                            "icon",
                            "error",
                            "fail",
                            f"page {page_id} references unknown icon '{icon_name}' "
                            f"(search comh.render.icons.search_icons)",
                            "deck_plan",
                        )
                    )
        diagram = (page.get("visual") or {}).get("diagram")
        if diagram:
            if diagram.get("evidence") and diagram["evidence"] not in evidence_items:
                findings.append(
                    Finding(
                        "deck_plan",
                        "ref-integrity",
                        "error",
                        "fail",
                        f"page {page_id} diagram references missing evidence "
                        f"'{diagram['evidence']}'",
                        "evidence",
                    )
                )
            # Dry-run mermaid → DrawioDocument (pure Python, no draw.io CLI) so
            # bad diagram syntax fails at validation, not at render time.
            from .render.diagrams import dry_convert

            error = dry_convert(str(diagram.get("mermaid", "")))
            if error:
                findings.append(
                    Finding(
                        "deck_plan",
                        "diagram",
                        "error",
                        "fail",
                        f"page {page_id} diagram does not compile: {error}",
                        "deck_plan",
                    )
                )
        callout = page.get("callout")
        if callout and callout.get("evidence") and callout["evidence"] not in evidence_items:
            findings.append(
                Finding(
                    "deck_plan",
                    "ref-integrity",
                    "error",
                    "fail",
                    f"page {page_id} callout references missing evidence '{callout['evidence']}'",
                    "evidence",
                )
            )
        if page.get("page_role") == "timeline" and len(page.get("support_points") or []) > 4:
            findings.append(
                Finding(
                    "deck_plan",
                    "layout",
                    "warn",
                    "pass",
                    f"page {page_id}: timeline has {len(page.get('support_points'))} milestones "
                    "(recommended 3-4) — excess items may cause layout crowding",
                    "deck_plan",
                )
            )
        if page.get("page_role") == "versus":
            columns = (page.get("visual") or {}).get("columns")
            if not (
                isinstance(columns, list)
                and len(columns) == 2
                and all(str(c).strip() for c in columns)
            ):
                findings.append(
                    Finding(
                        "deck_plan",
                        "layout",
                        "warn",
                        "pass",
                        f"page {page_id}: versus needs visual.columns: [left, right] "
                        "column labels (renderers will not invent them)",
                        "deck_plan",
                    )
                )
    return findings


def _address_error(page: dict, address: str) -> str | None:
    """Resolve one element address against a page; None when valid."""
    match = _ADDRESS.match(address)
    if not match:
        return (
            f"'{address}' is not a valid element address "
            f"(title | callout | visual | support_points[i] | metric_cards[i])"
        )
    base, index = match.group(1), match.group(2)
    if base not in _ELEMENT_BASES:
        return f"unknown element '{base}'"
    if base in ("title", "callout", "visual") and index is not None:
        return f"'{base}' takes no index"
    if base == "visual":
        visual = page.get("visual") or {}
        if not (visual.get("chart") or visual.get("diagram") or visual.get("asset_refs")):
            return "'visual' addressed but the page has no chart/diagram/figure"
    if base == "callout" and not page.get("callout"):
        return "'callout' addressed but the page has none"
    if base == "support_points":
        points = page.get("support_points") or []
        if index is None and not points:
            return "'support_points' addressed but the page has none"
        if index is not None and int(index) >= len(points):
            return f"support_points[{index}] out of range ({len(points)} points)"
    if base == "metric_cards":
        cards = page.get("metric_cards") or []
        if index is None and not cards:
            return "'metric_cards' addressed but the page has none"
        if index is not None and int(index) >= len(cards):
            return f"metric_cards[{index}] out of range ({len(cards)} cards)"
    return None


def validate_reveal(artifacts: dict[str, dict | None]) -> list[Finding]:
    """Reveal/emphasis steps: element addresses must resolve against the page,
    verbs/triggers come from the fragment vocabulary (unknown values warn)."""
    findings: list[Finding] = []
    deck = artifacts.get("deck_plan") or {}
    for page in deck.get("deck", {}).get("pages", []):
        page_id = page["id"]
        for field in ("reveal", "emphasis"):
            for entry in page.get(field) or []:
                if not isinstance(entry, dict):
                    continue  # legacy free-form note string
                for address in entry.get("elements") or []:
                    error = _address_error(page, str(address))
                    if error:
                        findings.append(
                            Finding(
                                "deck_plan",
                                "reveal-address",
                                "error",
                                "fail",
                                f"page {page_id} {field}: {error}",
                                "deck_plan",
                            )
                        )
                verb = entry.get("verb")
                if verb and verb not in _KNOWN_VERBS:
                    findings.append(
                        Finding(
                            "deck_plan",
                            "reveal-verb",
                            "warn",
                            "pass",
                            f"page {page_id} {field}: unknown verb '{verb}' "
                            f"(renderers ignore unknown verbs)",
                            "deck_plan",
                        )
                    )
                trigger = entry.get("trigger")
                if trigger and trigger not in _KNOWN_TRIGGERS:
                    findings.append(
                        Finding(
                            "deck_plan",
                            "reveal-trigger",
                            "warn",
                            "pass",
                            f"page {page_id} {field}: unknown trigger '{trigger}'",
                            "deck_plan",
                        )
                    )
    return findings


def validate_assets(artifacts: dict[str, dict | None], run_root: Path) -> list[Finding]:
    """Asset provenance: materials fetched into the run must be registered in
    ``assets/manifest.yaml`` (file, origin_url, license, fetched_at) and must
    exist on disk. Images are decoration, never evidence — this guards
    provenance, not grounding."""
    deck = artifacts.get("deck_plan") or {}
    refs: list[tuple[str, str]] = []
    for page in deck.get("deck", {}).get("pages", []):
        for item in (page.get("visual") or {}).get("asset_refs", []):
            entry = item if isinstance(item, dict) else {"ref": item}
            ref = str(entry.get("ref", "")).strip()
            if ref:
                refs.append((page["id"], ref))
        bg_spec = (page.get("visual") or {}).get("background") or page.get("background")
        if isinstance(bg_spec, dict):
            bg_asset = str(bg_spec.get("asset", "")).strip()
            if bg_asset:
                refs.append((page["id"], bg_asset))
    if not refs:
        return []
    manifest_path = run_root / "assets" / "manifest.yaml"
    if not manifest_path.is_file():
        return [
            Finding(
                "deck_plan",
                "asset-provenance",
                "info",
                "pass",
                f"{len({ref for _, ref in refs})} asset(s) in use without a manifest; "
                "materials fetched from outside should be registered in "
                "assets/manifest.yaml {file, origin_url, license, fetched_at}",
                "deck_plan",
            )
        ]
    registered = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    entries = {
        str(entry.get("file", "")).strip(): entry
        for entry in (registered.get("assets") or [])
        if isinstance(entry, dict)
    }
    findings: list[Finding] = []
    for name in sorted(entries):
        if not (run_root / name).is_file():
            findings.append(
                Finding(
                    "deck_plan",
                    "asset-provenance",
                    "error",
                    "fail",
                    f"manifest registers '{name}' but the file is missing",
                    "deck_plan",
                )
            )
    for page_id, ref in refs:
        if ref not in entries:
            findings.append(
                Finding(
                    "deck_plan",
                    "asset-provenance",
                    "warn",
                    "pass",
                    f"page {page_id} uses '{ref}' which assets/manifest.yaml does not "
                    "register (fetched materials must record origin and license)",
                    "deck_plan",
                )
            )
    return findings


def validate_theme(artifacts: dict[str, dict | None], run_root: Path) -> list[Finding]:
    """Quality floor for customized themes (AI-authored or hand-edited): the
    effective theme's contrast and legibility are machine-checked, so creative
    freedom never ships an unreadable deck. Checks the theme as requested
    (pre light-pinning) — pinning has its own hard-constraint finding."""
    deck = artifacts.get("deck_plan") or {}
    style = deck.get("deck", {}).get("style") or {}
    if not (style.get("template") or style.get("tokens_override")):
        return []  # default theme; the built-ins are guarded by their own test
    from .render.scrim import solve_scrim
    from .render.theme import background_is_light, contrast_ratio, resolve_style

    theme = resolve_style(style, allow_dark=True, run_root=run_root).theme
    findings: list[Finding] = []
    text_ratio = contrast_ratio(theme.text, theme.background)
    if text_ratio < 4.5:
        findings.append(
            Finding(
                "deck_plan",
                "theme-contrast",
                "error",
                "fail",
                f"theme '{theme.name}': text/background contrast {text_ratio:.1f}:1 "
                f"is below 4.5:1 — body text would be unreadable; darken the text "
                f"or lighten the background",
                "deck_plan",
            )
        )
    for role, color in (("muted", theme.muted), ("accent", theme.accent)):
        ratio = contrast_ratio(color, theme.background)
        if ratio < 3.0:
            findings.append(
                Finding(
                    "deck_plan",
                    "theme-contrast",
                    "warn",
                    "pass",
                    f"theme '{theme.name}': {role} color contrast {ratio:.1f}:1 is "
                    f"below 3:1 — captions/kicker/accents may be hard to see",
                    "deck_plan",
                )
            )
    if theme.is_light != background_is_light(theme.background):
        actual = "light" if background_is_light(theme.background) else "dark"
        findings.append(
            Finding(
                "deck_plan",
                "theme-declaration",
                "warn",
                "pass",
                f"theme '{theme.name}' declares is_light={theme.is_light} but its "
                f"background '{theme.background}' reads {actual}; dark-forbidding "
                f"briefs pin on the actual color, fix the flag",
                "deck_plan",
            )
        )
    for role, size, floor in (
        ("body", theme.body_size, 14),
        ("detail", theme.detail_size, 11),
        ("caption", theme.caption_size, 9),
    ):
        if size < floor:
            findings.append(
                Finding(
                    "deck_plan",
                    "theme-legibility",
                    "warn",
                    "pass",
                    f"theme '{theme.name}': {role} size {size}pt is below the "
                    f"{floor}pt legibility floor",
                    "deck_plan",
                )
            )

    # Check empirical background contrast across all pages
    for page in deck.get("deck", {}).get("pages", []):
        bg_spec = (page.get("visual") or {}).get("background") or page.get("background")
        if isinstance(bg_spec, dict) and bg_spec.get("asset"):
            asset_path = run_root / str(bg_spec["asset"])
            if asset_path.is_file():
                scrim_res = solve_scrim(
                    asset_path,
                    theme.text,
                    theme.background,
                    base_alpha=float(bg_spec.get("opacity") or 0.0),
                )
                if not scrim_res.passed:
                    findings.append(
                        Finding(
                            "deck_plan",
                            "background-contrast",
                            "error",
                            "fail",
                            f"page {page['id']}: background image contrast against theme text "
                            f"({scrim_res.contrast:.1f}:1) is below 4.5:1 even at alpha=0.90",
                            "deck_plan",
                        )
                    )
    return findings


def validate_hard_constraints(
    artifacts: dict[str, dict | None],
    report_md_text: str | None,
    run_root: Path | None = None,
) -> list[Finding]:
    """Check only stages in scope; pending content never blocks its own brief."""
    from .render.theme import resolve_style

    findings = []
    brief = artifacts.get("brief") or {}
    for medium in brief.get("media", []):
        if (medium["medium"], medium["surface"]) not in MEDIA_OUTPUTS:
            findings.append(
                Finding(
                    "brief",
                    "media",
                    "error",
                    "fail",
                    f"unsupported output: {medium['medium']}/{medium['surface']}",
                )
            )
    constraints = hard_constraints(brief)
    ids = [c["id"] for c in constraints]
    if len(ids) != len(set(ids)):
        findings.append(
            Finding(
                "brief", "hard-constraint", "error", "fail", "hard constraint IDs must be unique"
            )
        )
    for constraint in constraints:
        check, scope = constraint["check"], constraint["scope"]
        text, phrase = constraint["text"], str(constraint.get("value", ""))
        if check == "manual":
            findings.append(
                Finding(
                    "brief",
                    "hard-constraint",
                    "warn",
                    "pass",
                    f"constraint '{text}' has no machine check; retain as hard "
                    f"and record manual acceptance in the final review ({constraint['id']})",
                )
            )
            continue
        if check == "light_background":
            if artifacts.get("deck_plan") is None:
                continue
            style = artifacts["deck_plan"].get("deck", {}).get("style")
            choice = resolve_style(style, allow_dark=False, run_root=run_root)
            findings.append(
                Finding(
                    "deck_plan",
                    "hard-constraint",
                    "error" if choice.forced_light else "info",
                    "fail" if choice.forced_light else "pass",
                    f"constraint '{text}': effective deck background is "
                    f"{'dark; choose a light palette' if choice.forced_light else 'light'}",
                    "deck_plan",
                )
            )
            continue
        targets = {}
        if scope in ("all", "deck") and artifacts.get("deck_plan") is not None:
            targets["deck_plan"] = deck_text(artifacts["deck_plan"])
        if scope in ("all", "report"):
            if report_md_text is not None:
                targets["report_md"] = prose(report_md_text)
            elif artifacts.get("report_plan") is not None:
                plan = artifacts["report_plan"]
                targets["report_plan"] = "\n".join(
                    s["heading"] + " " + " ".join(s.get("must_include", []))
                    for s in plan.get("sections", [])
                )
        for owner, content in targets.items():
            violates = (check == "contains" and phrase not in content) or (
                check == "forbidden" and phrase in content
            )
            if violates:
                findings.append(
                    Finding(
                        owner,
                        "hard-constraint",
                        "error",
                        "fail",
                        f"constraint '{text}' ({check}: '{phrase}') violated in {owner}",
                        owner,
                    )
                )
    return findings


def deck_text(plan: dict) -> str:
    """Displayed text only: extension metadata cannot satisfy content requirements."""
    texts = [plan.get("deck", {}).get("title", "")]
    for page in plan.get("deck", {}).get("pages", []):
        texts += [page.get("title", ""), page.get("kicker", "")]
        for point in page.get("support_points", []):
            texts += (
                [point.get("point", ""), point.get("detail", "")]
                if isinstance(point, dict)
                else [point]
            )
        texts += [card.get("label", "") for card in page.get("metric_cards", [])]
        texts += [(page.get("callout") or {}).get("text", "")]
        visual = page.get("visual") or {}
        texts += visual.get("columns", [])
        texts += [entry.get("label", "") for entry in (visual.get("chart") or {}).get("series", [])]
        texts += [a.get("caption", "") for a in visual.get("asset_refs", []) if isinstance(a, dict)]
        texts += [(visual.get("diagram") or {}).get("caption", "")]
    return "\n".join(str(t) for t in texts)


def run_all(run_root: Path, keys: set[str] | None = None) -> list[Finding]:
    manifest = Manifest.load(run_root)
    if keys is None:
        brief, _ = load_artifact(run_root, "brief")
        keys = required_artifacts(brief or {})
    artifacts = {}
    findings = []
    for key in sorted(keys - {"report_md"}):
        data, schema_findings = load_artifact(run_root, key)
        artifacts[key] = data
        findings.extend(schema_findings)
    # Never run semantic validators on malformed objects or incomplete references.
    if any(f.severity == "error" for f in findings):
        return findings
    report_md_text = None
    if "report_md" in keys:
        report_path = manifest.artifact_path("report_md")
        if report_path.is_file():
            report_md_text = report_path.read_text(encoding="utf-8")
        else:
            findings.append(
                Finding("report_md", "schema", "error", "fail", "report source missing")
            )
    from .style_lint import validate_style

    findings += validate_style(artifacts, report_md_text)
    if artifacts.get("evidence") is not None:
        findings += validate_sources(artifacts, run_root)
    if all(artifacts.get(k) is not None for k in ("evidence", "narrative")):
        findings += validate_refs(artifacts)
        findings += validate_claims(artifacts)
        findings += validate_numbers(artifacts, report_md_text)
        findings += validate_coverage(artifacts)
        findings += validate_visuals(artifacts)
        findings += validate_reveal(artifacts)
        findings += validate_report(artifacts, report_md_text)
    if artifacts.get("deck_plan") is not None:
        findings += validate_assets(artifacts, run_root)
        findings += validate_theme(artifacts, run_root)
    if artifacts.get("brief") is not None:
        findings += validate_hard_constraints(artifacts, report_md_text, run_root)
    return findings


def write_findings(run_root: Path, findings: list[Finding]) -> Path:
    from .qa import preserve_legacy_review

    preserve_legacy_review(run_root)
    qa_dir = run_root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    path = qa_dir / "findings.yaml"
    payload = {
        "count": {"error": 0, "warn": 0, "info": 0},
        "findings": [f.as_dict() for f in findings],
    }
    for f in findings:
        payload["count"][f.severity] += 1
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


__all__ = [
    "run_all",
    "write_findings",
    "validate_assets",
    "validate_claims",
    "validate_coverage",
    "validate_hard_constraints",
    "validate_numbers",
    "validate_refs",
    "validate_reveal",
    "validate_sources",
    "validate_theme",
    "validate_visuals",
]

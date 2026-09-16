"""Presentation density is an explicit authoring policy, independent of appearance."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from functools import cache
from importlib.resources import files

from .artifacts import Finding
from .visible_text import page_texts


@cache
def profiles() -> dict:
    return json.loads(
        files("comh").joinpath("presets/presentation.json").read_text(encoding="utf-8")
    )


def applicable(brief: dict) -> bool:
    return any(m.get("surface") == "presentation" for m in brief.get("media", []))


def resolve_profile(brief: dict) -> dict:
    config = brief.get("presentation") or {}
    if not isinstance(config, dict):
        raise ValueError("brief.presentation must be an object")
    setting = config.get("setting", "general")
    name = config.get("profile") or ("academic-rich" if setting == "academic" else "balanced")
    if name not in profiles():
        raise ValueError(f"unknown presentation profile: {name}")
    result = deepcopy(profiles()[name])
    overrides = config.get("overrides") or {}
    result["text_budget"].update(overrides.get("text_budget") or {})
    for key in ("substantive_blocks", "layout_patterns"):
        if key in overrides:
            result[key] = deepcopy(overrides[key])
    result.update(
        profile=name, setting=setting, selection="explicit" if config.get("profile") else "default"
    )
    result["boundary"] = (
        "Authoring guidance, not a quota or a semantic quality score. "
        "Do not invent evidence, force blocks, shrink fonts or import appearance."
    )
    return result


def policy_errors(brief: dict) -> list[str]:
    if not applicable(brief):
        return []
    config = brief.get("presentation")
    if not isinstance(config, dict) or config.get("setting") not in {"academic", "general"}:
        return [
            "brief.presentation.setting must record academic/general; "
            "explicit profile overrides its default"
        ]
    try:
        profile = resolve_profile(brief)
    except ValueError as error:
        return [str(error)]
    ranges = {**profile["text_budget"], "substantive_blocks": profile["substantive_blocks"]}
    return [
        f"presentation {key}: lower bound must not exceed upper bound"
        for key, value in ranges.items()
        if value[0] > value[1]
    ]


def validate_density(artifacts: dict) -> list[Finding]:
    brief = artifacts.get("brief") or {}
    if not applicable(brief) or policy_errors(brief):
        return []
    profile = resolve_profile(brief)
    deck = artifacts.get("deck_plan") or {}
    if deck.get("draft"):
        return []  # Outline scaffolding is not finished copy.
    chinese = brief.get("language", "").lower().startswith("zh")
    low, high = profile["text_budget"]["zh_chars" if chinese else "words"]
    findings = []
    for page in deck.get("deck", {}).get("pages", []):
        if page.get("page_role") in {"cover", "agenda", "section_divider", "closing", "appendix"}:
            continue
        visual = page.get("visual") or {}
        content = "\n".join(t for _, t in page_texts(page))
        count = (
            len(re.sub(r"\s", "", content)) if chinese else len(re.findall(r"\b[\w'-]+\b", content))
        )
        has_visual = any(visual.get(k) for k in ("chart", "diagram", "asset_refs", "table"))
        blocks = len(page.get("support_points") or []) + bool(page.get("metric_cards")) + has_visual
        too_sparse = count < low and not has_visual
        if too_sparse or count > high:
            issue = "sparse" if too_sparse else "dense"
            findings.append(
                Finding(
                    "deck_plan",
                    f"density:{issue}",
                    "warn",
                    "fail",
                    f"page {page['id']}: {profile['profile']} has {count} "
                    f"{'characters' if chinese else 'words'}, "
                    f"{blocks} structural blocks (reference {low}–{high}); "
                    "review evidence/explanation and actual layout. "
                    "Do not pad, invent facts or shrink type.",
                    "deck_plan",
                )
            )
    # A long paragraph with a callout is still a text page. Flag repeated text-only
    # bodies for human review without prescribing a quota or inventing evidence.
    streak = []
    for page in deck.get("deck", {}).get("pages", []) + [{}]:
        visual = page.get("visual") or {}
        text_only = (
            bool(page)
            and page.get("page_role", "content") == "content"
            and not any(visual.get(k) for k in ("chart", "diagram", "asset_refs", "table"))
            and visual.get("arrangement") != "columns"
        )
        if text_only:
            streak.append(page["id"])
        else:
            if len(streak) >= 3:
                findings.append(
                    Finding(
                        "deck_plan",
                        "presentation:text-only-sequence",
                        "warn",
                        "fail",
                        f"pages {', '.join(streak)} repeat text-only bodies; "
                        "review whether comparison, mechanism or experimental evidence "
                        "needs a table, diagram or chart. Do not add decoration to clear "
                        "this warning.",
                        "deck_plan",
                    )
                )
            streak = []
    return findings


_CLAUSE_SPLIT = re.compile(r"[；;]")


def validate_packing(artifacts: dict) -> list[Finding]:
    """Signal overloaded slide copy: one detail line that semicolon-chains a
    list of facts ("did A; did B; did C; did D") instead of being one
    elaborated point. Flowing explanatory prose with full sentences is rich
    content, not packing — only semicolon chains count.

    Unlike validate_density this runs on drafts too — packing is a structural
    problem visible while the outline is still being aligned, not a
    completeness signal that waits for finished copy.
    """
    brief = artifacts.get("brief") or {}
    if not applicable(brief) or policy_errors(brief):
        return []
    deck = artifacts.get("deck_plan") or {}
    findings = []
    for page in deck.get("deck", {}).get("pages", []):
        if page.get("page_role") in {"cover", "agenda", "section_divider", "closing", "appendix"}:
            continue
        for element, text in page_texts(page):
            if not element.endswith(".detail"):
                continue
            parts = [part for part in _CLAUSE_SPLIT.split(text or "") if part.strip()]
            if len(parts) >= 4:
                findings.append(
                    Finding(
                        "deck_plan",
                        "density:packed-detail",
                        "warn",
                        "fail",
                        f"page {page['id']} {element} semicolon-chains {len(parts)} facts "
                        "into one line; it is a structure, not a sentence — split it into "
                        "more point/detail pairs or a richer carrier (list, table, diagram). "
                        "Do not delete facts or shrink type to clear this warning.",
                        "deck_plan",
                    )
                )
    return findings


def presentation_structure_errors(page: dict) -> list[str]:
    """Check consumed layout combinations, not whether a reading path is persuasive."""
    visual = page.get("visual") or {}
    carriers = [k for k in ("chart", "diagram", "asset_refs", "table") if visual.get(k)]
    errors = []
    if len(carriers) > 1:
        errors.append("choose one primary visual carrier; competing carriers would be dropped")
    arrangement = visual.get("arrangement", "split")
    if arrangement == "full" and page.get("support_points"):
        errors.append(
            "full arrangement cannot also contain support_points; use a callout or split layout"
        )
    if arrangement == "columns" and (
        carriers or page.get("metric_cards") or not 2 <= len(page.get("support_points") or []) <= 3
    ):
        errors.append(
            "columns requires two or three support_points and no separate visual/metric cards"
        )
    role = page.get("page_role", "content")
    if (visual.get("table") or visual.get("diagram")) and role in {
        "cover",
        "agenda",
        "section_divider",
        "closing",
        "timeline",
        "versus",
        "fullscreen_backdrop",
    }:
        errors.append("this page_role does not render tables/diagrams; use content or hero_split")
    if arrangement != "split" and role != "content":
        errors.append("full/columns arrangement requires content page_role")
    table = visual.get("table") or {}
    columns = table.get("columns", [])
    if any(len(row) != len(columns) for row in table.get("rows", [])):
        errors.append("every table row must match its column count")
    weights = table.get("column_weights")
    if weights is not None and (len(weights) != len(columns) or any(v <= 0 for v in weights)):
        errors.append("table column_weights must be positive and match columns")
    return errors

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
        has_visual = any(visual.get(k) for k in ("chart", "diagram", "asset_refs"))
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
    return findings

"""Presentation density is an explicit authoring policy, independent of appearance.

Profiles are data, like themes. The three built-ins cover the common settings;
a run adds its own under ``profiles/presentation/<name>.yaml`` when its scenario
(investor pitch, incident review, thesis defence) needs different budgets and
guidance. A custom profile may extend a built-in, and it may never drop the
boundary statement: density is authoring guidance, never a word quota nor
permission to invent facts.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from functools import cache
from importlib.resources import files
from pathlib import Path

import yaml

from .artifacts import Finding
from .visible_text import page_texts

BOUNDARY = (
    "Authoring guidance, not a quota or a semantic quality score. "
    "Do not invent evidence, force blocks, shrink fonts or import appearance."
)

# Scripts whose readable density is measured in characters rather than words.
# A run in one of these counted by word would be measured with the wrong ruler.
CHARACTER_SCRIPTS = ("zh", "ja", "ko", "yue", "wuu", "nan", "hak")

_PROFILE_DIR = "profiles/presentation"
_RANGE_KEYS = ("substantive_blocks",)


@cache
def builtin_profiles() -> dict:
    return json.loads(
        files("comh").joinpath("presets/presentation.json").read_text(encoding="utf-8")
    )


def counts_characters(language: str | None) -> bool:
    return str(language or "").lower().replace("_", "-").split("-")[0] in CHARACTER_SCRIPTS


def budget_key(language: str | None) -> str:
    """Which text_budget range applies. ``zh_chars`` is the historical name of
    the character budget and stays the key for every character script."""
    return "zh_chars" if counts_characters(language) else "words"


def _profile_errors(name: str, data: dict) -> list[str]:
    errors = []
    budget = data.get("text_budget")
    if not isinstance(budget, dict) or not budget:
        errors.append(f"presentation profile '{name}': text_budget must be an object")
        budget = {}
    for key, value in list(budget.items()) + [
        (k, data.get(k)) for k in _RANGE_KEYS if k in data
    ]:
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(isinstance(v, int) and v >= 0 for v in value)
        ):
            errors.append(f"presentation profile '{name}': {key} must be two integers >= 0")
        elif value[0] > value[1]:
            errors.append(f"presentation {key}: lower bound must not exceed upper bound")
    if "substantive_blocks" not in data:
        errors.append(f"presentation profile '{name}': substantive_blocks is required")
    return errors


def profiles(run_root: Path | None = None) -> dict:
    """Built-in profiles plus any the run defines. Run profiles win by name."""
    result = deepcopy(builtin_profiles())
    directory = (run_root / _PROFILE_DIR) if run_root else None
    if directory is None or not directory.is_dir():
        return result
    for path in sorted(directory.iterdir()):
        if path.suffix not in {".yaml", ".yml", ".json"} or not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as error:
            raise ValueError(
                f"presentation profile '{path.name}' is unreadable: {error}"
            ) from error
        if not isinstance(data, dict):
            raise ValueError(f"presentation profile '{path.name}' must be a mapping")
        base = deepcopy(result.get(data.get("extends"), {})) if data.get("extends") else {}
        if data.get("extends") and not base:
            raise ValueError(
                f"presentation profile '{path.stem}' extends unknown profile "
                f"'{data['extends']}'"
            )
        merged = {**base, **{k: v for k, v in data.items() if k != "extends"}}
        if isinstance(base.get("text_budget"), dict) and isinstance(data.get("text_budget"), dict):
            merged["text_budget"] = {**base["text_budget"], **data["text_budget"]}
        errors = _profile_errors(path.stem, merged)
        if errors:
            raise ValueError("; ".join(errors))
        merged.setdefault("label", path.stem)
        result[path.stem] = merged
    return result


def applicable(brief: dict) -> bool:
    return any(m.get("surface") == "presentation" for m in brief.get("media", []))


def resolve_profile(brief: dict, run_root: Path | None = None) -> dict:
    config = brief.get("presentation") or {}
    if not isinstance(config, dict):
        raise ValueError("brief.presentation must be an object")
    setting = config.get("setting", "general")
    available = profiles(run_root)
    name = config.get("profile") or ("academic-rich" if setting == "academic" else "balanced")
    if name not in available:
        raise ValueError(
            f"unknown presentation profile: {name} "
            f"(available: {', '.join(sorted(available))}; "
            f"add one under {_PROFILE_DIR}/<name>.yaml)"
        )
    result = deepcopy(available[name])
    overrides = config.get("overrides") or {}
    result["text_budget"].update(overrides.get("text_budget") or {})
    for key in ("substantive_blocks", "layout_patterns", "content_guidance"):
        if key in overrides:
            result[key] = deepcopy(overrides[key])
    result.update(
        profile=name,
        setting=setting,
        selection="explicit" if config.get("profile") else "default",
        builtin=name in builtin_profiles(),
    )
    result["boundary"] = BOUNDARY  # never overridable, whatever a profile file says
    return result


def policy_errors(brief: dict, run_root: Path | None = None) -> list[str]:
    if not applicable(brief):
        return []
    config = brief.get("presentation")
    if not isinstance(config, dict) or config.get("setting") not in {"academic", "general"}:
        return [
            "brief.presentation.setting must record academic/general; "
            "explicit profile overrides its default"
        ]
    try:
        profile = resolve_profile(brief, run_root)
    except ValueError as error:
        return [str(error)]
    return _profile_errors(profile.get("profile", "?"), profile)

def validate_density(artifacts: dict, run_root: Path | None = None) -> list[Finding]:
    brief = artifacts.get("brief") or {}
    if not applicable(brief) or policy_errors(brief, run_root):
        return []
    profile = resolve_profile(brief, run_root)
    deck = artifacts.get("deck_plan") or {}
    if deck.get("draft"):
        return []  # Outline scaffolding is not finished copy.
    chinese = counts_characters(brief.get("language"))
    low, high = profile["text_budget"][budget_key(brief.get("language"))]
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
            and visual.get("arrangement", "split") in {"split", "full"}
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
# A labeled segment inside a detail line: "优点：…", "Cost: …".
_LABELED = re.compile(r"^\s*([^：:，,。.；;]{1,12})\s*[：:]\s*\S")
# Ordinal openers. Digits and circled numbers are script-neutral; the word
# markers are the zh/en pack (see locale_support.RULE_PACKS["layout-shape"]).
_ORDINAL_NEUTRAL = re.compile(r"^\s*(?:\(?\d{1,2}[.)、．]|[①-⑩])")
_ORDINAL_WORDS = {
    "zh": re.compile(
        r"^\s*(?:第[一二三四五六七八九十\d]+[步阶]|步骤\s*[一二三四五六七八九十\d]|首先|其次|然后|接着|最后)"
    ),
    "en": re.compile(
        r"^\s*(?:step\s*\d+|first(?:ly)?\b|second(?:ly)?\b|then\b|next\b|finally\b)", re.I
    ),
}
_QUESTION = re.compile(r"[?？]\s*$")


def _shape_hints(page: dict, language: str) -> list[tuple[str, str]]:
    """(check, message) for list pages whose items already carry a structure
    one of the text forms or a table would show directly."""
    visual = page.get("visual") or {}
    if visual.get("arrangement", "split") not in {"split"} or any(
        visual.get(k) for k in ("chart", "diagram", "asset_refs", "table")
    ):
        return []
    points = page.get("support_points") or []
    parts = [
        (str(e.get("point", "")), str(e.get("detail") or ""))
        if isinstance(e, dict)
        else (str(e), "")
        for e in points
    ]
    hints = []
    label_sets = []
    for _, detail in parts:
        labels = [
            m.group(1).strip() for c in _CLAUSE_SPLIT.split(detail) if (m := _LABELED.match(c))
        ]
        label_sets.append(tuple(labels))
    shared = [labels for labels in label_sets if len(labels) >= 2]
    if len(shared) >= 3 and len(set(shared)) == 1:
        hints.append(
            (
                "layout:suggest-table",
                f"{len(shared)} items repeat the same labeled fields "
                f"({' / '.join(shared[0])}); that is a table — one row per item, one column "
                "per field (visual.table).",
            )
        )
    words = _ORDINAL_WORDS.get(language)
    ordinal = sum(
        bool(_ORDINAL_NEUTRAL.match(point) or (words and words.match(point))) for point, _ in parts
    )
    if len(parts) >= 3 and ordinal >= len(parts) - 1:
        hints.append(
            (
                "layout:suggest-steps",
                "the items are written as an ordered sequence; arrangement: steps numbers "
                "them and shows the order instead of spelling it in the copy.",
            )
        )
    questions = sum(bool(_QUESTION.search(point)) for point, _ in parts)
    if len(parts) >= 2 and questions >= 2 and all(detail for _, detail in parts):
        hints.append(
            (
                "layout:suggest-qa",
                "the items are questions with answers; arrangement: qa aligns each question "
                "with its answer.",
            )
        )
    return hints


def validate_packing(artifacts: dict, run_root: Path | None = None) -> list[Finding]:
    """Signal overloaded slide copy: one detail line that semicolon-chains a
    list of facts ("did A; did B; did C; did D") instead of being one
    elaborated point. Flowing explanatory prose with full sentences is rich
    content, not packing — only semicolon chains count.

    Unlike validate_density this runs on drafts too — packing is a structural
    problem visible while the outline is still being aligned, not a
    completeness signal that waits for finished copy.
    """
    brief = artifacts.get("brief") or {}
    if not applicable(brief) or policy_errors(brief, run_root):
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
        from .locale_support import language_tag

        for check, message in _shape_hints(page, language_tag(brief)):
            findings.append(
                Finding(
                    "deck_plan",
                    check,
                    "warn",
                    "fail",
                    f"page {page['id']}: {message} Keep the list if the order or pairing "
                    "is not the point.",
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
    no_carrier_roles = {"cover", "agenda", "section_divider", "closing", "timeline"}
    if (visual.get("table") or visual.get("diagram")) and role in no_carrier_roles | {
        "fullscreen_backdrop"
    }:
        errors.append("this page_role does not render tables/diagrams; use content or hero_split")
    if role == "versus":
        if visual.get("diagram"):
            errors.append("versus does not render diagrams; use content or hero_split")
        if visual.get("table") and page.get("support_points"):
            errors.append(
                "a versus table replaces the two columns; move support_points into table rows"
            )
    if arrangement != "split" and role != "content":
        errors.append(f"{arrangement} arrangement requires content page_role")
    from .render.table import table_errors
    from .render.text_forms import form_errors

    errors += form_errors(page)
    if visual.get("table"):
        errors += table_errors(visual["table"])
    return errors


# Content-like roles whose body layout counts toward layout variety.
_FRAME_ROLES = {"cover", "agenda", "section_divider", "closing", "appendix"}


def layout_signature(page: dict) -> str:
    """What a page's body looks like: role, text form and primary carrier.
    The same vocabulary the outline view shows as each page's carrier."""
    visual = page.get("visual") or {}
    carrier = next(
        (
            name
            for key, name in (
                ("chart", "chart"),
                ("table", "table"),
                ("diagram", "diagram"),
                ("asset_refs", "image"),
            )
            if visual.get(key)
        ),
        None,
    )
    arrangement = visual.get("arrangement", "split")
    if carrier is None:
        body = "text" if arrangement in {"split", "full"} else f"text:{arrangement}"
    else:
        body = carrier
    role = page.get("page_role", "content")
    return body if role == "content" else f"{role}/{body}"


def validate_layout_variety(artifacts: dict) -> list[Finding]:
    """Advisory: the same body layout repeated page after page, or dominating
    the deck. Layout should follow each page's information relation; a repeat
    that is deliberate can stay — this asks for a look, never a quota."""
    deck = artifacts.get("deck_plan") or {}
    if deck.get("draft"):
        return []
    pages = [
        p for p in deck.get("deck", {}).get("pages", []) if p.get("page_role") not in _FRAME_ROLES
    ]
    findings = []
    streak: list[str] = []
    previous = None
    for page in pages + [None]:
        signature = layout_signature(page) if page else None
        if signature is not None and signature == previous:
            streak.append(page["id"])
            continue
        if len(streak) >= 3:
            findings.append(
                Finding(
                    "deck_plan",
                    "presentation:repeated-layout",
                    "warn",
                    "fail",
                    f"pages {', '.join(streak)} repeat the same body layout ({previous}); "
                    "check each page's information relation — sequence (steps), parallel "
                    "items (grid/columns), claim with conditions (statement), questions "
                    "(qa), terms (definition), progress (status), shared dimensions "
                    "(table). Keep the repeat only if the relation really is the same.",
                    "deck_plan",
                )
            )
        streak = [page["id"]] if page else []
        previous = signature
    counts: dict[str, int] = {}
    for page in pages:
        signature = layout_signature(page)
        counts[signature] = counts.get(signature, 0) + 1
    if len(pages) >= 5:
        signature, count = max(counts.items(), key=lambda item: item[1])
        if count / len(pages) > 0.6:
            findings.append(
                Finding(
                    "deck_plan",
                    "presentation:layout-monotony",
                    "warn",
                    "fail",
                    f"{count} of {len(pages)} body pages use the same layout ({signature}); "
                    "review whether the content relations differ. Do not vary layout for "
                    "its own sake or add decoration to clear this.",
                    "deck_plan",
                )
            )
    return findings

"""Which deterministic checks actually cover a run's language.

The pattern checkers are language-specific: `style_lint` carries a Chinese
marker vocabulary plus a small English tell set, `audience_lint` is Chinese
regex only, and the legacy hard-constraint parser in `contracts` recognizes
Chinese phrasings. A run written in a language no pack covers passes every one
of those checks — and a silent pass is indistinguishable from clean copy.

So say it out loud. These findings do not block; they tell the agent and the
user which surfaces still need human judgment, the same way a missing headless
browser reports that geometry findings are not guaranteed.
"""

from __future__ import annotations

from .artifacts import Finding

# Languages each rule pack was actually written for.
RULE_PACKS: dict[str, tuple[frozenset[str], str]] = {
    "style": (frozenset({"zh", "en"}), "AI-tell / voice detection (comh/style_lint.py)"),
    "audience": (frozenset({"zh"}), "production-language leak detection (comh/audience_lint.py)"),
    "constraints": (
        frozenset({"zh"}),
        "legacy free-text hard-constraint parsing (comh/contracts.py)",
    ),
    "layout-shape": (
        frozenset({"zh", "en"}),
        "ordinal-word step detection for layout hints (comh/presentation_profile.py); "
        "digit, question-mark and labeled-field hints still run",
    ),
}


def language_tag(brief: dict) -> str:
    return str(brief.get("language") or "").lower().replace("_", "-").split("-")[0]


def uncovered_packs(brief: dict) -> list[str]:
    tag = language_tag(brief)
    if not tag:
        return []
    return sorted(name for name, (langs, _) in RULE_PACKS.items() if tag not in langs)


def coverage_findings(brief: dict | None) -> list[Finding]:
    """One finding per checker that does not cover this run's language."""
    brief = brief or {}
    tag = language_tag(brief)
    if not tag:
        return []
    findings = []
    for name in uncovered_packs(brief):
        languages, what = RULE_PACKS[name]
        findings.append(
            Finding(
                "brief",
                f"locale:{name}-not-covered",
                "warn",
                "fail",
                f"language '{tag}' has no {name} rule pack "
                f"(covered: {', '.join(sorted(languages))}); {what} did not run. "
                "A clean report does not mean this surface was checked — review it by hand "
                "or add the vocabulary for this language.",
                "brief",
            )
        )
    return findings

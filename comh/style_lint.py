"""Deterministic AI-tell detection over deck and report text.

Inspired by the humanizer / avoid-ai-writing practice: a fixed detector pass
that runs before and after rewriting (detect -> rewrite -> re-detect), so
"plain language" is enforced by findings, not by hope.

Rules are data; extend the vocabulary rather than the code. The default
profile is "plain" — but style is a per-run contract: brief.voice.rules can
relax rules (a punchy keynote WANTS em-dash punchlines) or tighten them
(extra forbidden words, extra metaphor markers), and brief.voice.style names
the register for the model. The detector enforces the CHOSEN style, not a
house style.

What the plain profile flags (all warn-level, owning artifact always set):

- em-dash punchlines: "陈述——短促金句" is THE structural AI tell in Chinese
  deck language; one per deck is a stylistic choice, several per page is a
  voice. Titles and callouts should not carry any.
- metaphor markers: an open vocabulary of vivid-anthropomorphism words
  (伤害、立尺子、组合拳…) — plain technical language says the thing itself.
- the "不是 X，而是 Y" contrast frame, high-frequency tell when it repeats.
- English tells: em-dash clauses, "not just X but Y", and the
  delve/crucial/seamless word family.

Rules are data; extend the vocabulary rather than the code.
"""

from __future__ import annotations

import re

from .artifacts import Finding

# Open vocabulary — extend freely; these are heuristics, not grammar laws.
METAPHOR_MARKERS = (
    "伤害",
    "打架",
    "立尺子",
    "组合拳",
    "护城河",
    "赛道",
    "赋能",
    "抓手",
    "药方",
    "生病",
    "讲故事",
    "靶点",
)

_EM_DASH = "——"
_NOT_X_BUT_Y = re.compile(r"不是[^，。；\n]{1,12}[，,]\s*(?:而是|是)")
_EN_TELL_WORDS = re.compile(
    r"\b(delve|crucial|seamless|leverage|holistic|robustly|tapestry)\b", re.IGNORECASE
)
_EN_EM_DASH_CLAUSE = re.compile(r"\s—\s[^.;\n]{3,60}[.!?)\]\"']*$")
_EN_NOT_JUST = re.compile(r"not just\b[^.;\n]{1,40}\bbut\b", re.IGNORECASE)


# built-in relaxations by style name: rules switched off for that register
_STYLE_RELAX = {
    "punchy": ("em-dash",),
    "formal": ("em-dash",),
    "academic": (),
    "plain": (),
}


class VoiceConfig:
    """The per-run language style contract (from brief.voice).

    Style is per-medium: deck language is spoken (short, sayable) and report
    language is written prose (complete sentences) — brief.voice.deck and
    brief.voice.report override the global register for their surface, with
    rules merging additively.
    """

    def __init__(self, voice: dict | None, override: dict | None = None) -> None:
        voice = voice or {}
        override = override or {}
        style = str(override.get("style") or voice.get("style") or "plain").lower()
        self.style = style
        self.relaxed: set[str] = set(_STYLE_RELAX.get(style, ()))
        merged_rules: dict = {}
        for block in (voice.get("rules"), override.get("rules")):
            for key, values in (block or {}).items():
                merged_rules.setdefault(key, []).extend(values or [])
        self.relaxed |= {str(r) for r in merged_rules.get("relax") or []}
        self.extra_forbidden = [str(w) for w in merged_rules.get("extra_forbidden") or []]
        self.markers = METAPHOR_MARKERS + tuple(
            str(m) for m in merged_rules.get("extra_metaphor_markers") or []
        )

    def enforces(self, rule: str) -> bool:
        """True when this rule is active for the run (not relaxed away)."""
        return rule not in self.relaxed


def _page_texts(page: dict) -> list[tuple[str, str]]:
    """(element, text) pairs of the speakable surface of one page."""
    pairs: list[tuple[str, str]] = [("title", str(page.get("title", "")))]
    for index, entry in enumerate(page.get("support_points") or []):
        if isinstance(entry, dict):
            pairs.append((f"support_points[{index}]", str(entry.get("point", ""))))
            if entry.get("detail"):
                pairs.append((f"support_points[{index}].detail", str(entry["detail"])))
        else:
            pairs.append((f"support_points[{index}]", str(entry)))
    if page.get("callout"):
        pairs.append(("callout", str(page["callout"].get("text", ""))))
    return [(element, text) for element, text in pairs if text]


def lint_text(
    page_id: str, element: str, text: str, voice: VoiceConfig | None = None
) -> list[Finding]:
    findings: list[Finding] = []
    voice = voice or VoiceConfig(None)
    em_dashes = text.count(_EM_DASH)
    if em_dashes and element in ("title", "callout") and voice.enforces("em-dash"):
        findings.append(
            Finding(
                "deck_plan",
                "style:em-dash",
                "warn",
                "fail",
                f"page {page_id} {element}: em-dash punchline in a title/callout — "
                f"write the plain statement instead "
                f'("{text[:36]}…")',
                "deck_plan",
            )
        )
    elif em_dashes > 1 and voice.enforces("em-dash"):
        findings.append(
            Finding(
                "deck_plan",
                "style:em-dash",
                "warn",
                "fail",
                f"page {page_id} {element}: {em_dashes} em-dash punchlines in one "
                f"block — keep at most one, prefer plain sentences",
                "deck_plan",
            )
        )
    for marker in voice.markers:
        if marker in text:
            findings.append(
                Finding(
                    "deck_plan",
                    "style:metaphor",
                    "warn",
                    "fail",
                    f"page {page_id} {element}: metaphor marker '{marker}' — say the "
                    f"technical fact directly; gloss jargon in half a sentence "
                    f"instead of building an analogy",
                    "deck_plan",
                )
            )
    if len(_NOT_X_BUT_Y.findall(text)) >= 2 and voice.enforces("contrast-frame"):
        findings.append(
            Finding(
                "deck_plan",
                "style:contrast-frame",
                "warn",
                "fail",
                f"page {page_id} {element}: repeated '不是X，而是Y' frames — the "
                f"contrast construction is an AI tell at this density",
                "deck_plan",
            )
        )
    if _EN_TELL_WORDS.search(text) and voice.enforces("en-tell"):
        findings.append(
            Finding(
                "deck_plan",
                "style:en-tell",
                "warn",
                "fail",
                f"page {page_id} {element}: AI-favored English wording "
                f"({_EN_TELL_WORDS.search(text).group(0)}) — pick the concrete word",
                "deck_plan",
            )
        )
    if (_EN_EM_DASH_CLAUSE.search(text) or _EN_NOT_JUST.search(text)) and voice.enforces("en-tell"):
        findings.append(
            Finding(
                "deck_plan",
                "style:en-tell",
                "warn",
                "fail",
                f"page {page_id} {element}: em-dash clause or 'not just X but Y' — "
                f"use a plain sentence",
                "deck_plan",
            )
        )
    return findings


def lint_report(text: str, voice: VoiceConfig | None = None) -> list[Finding]:
    findings: list[Finding] = []
    voice = voice or VoiceConfig(None)
    for number, paragraph in enumerate(text.split("\n\n"), 1):
        paragraph = paragraph.strip()
        if not paragraph or paragraph.startswith(("|", "```", "#", "!")):
            continue
        em_dashes = paragraph.count(_EM_DASH)
        if em_dashes > 1 and voice.enforces("em-dash"):
            findings.append(
                Finding(
                    "report_md",
                    "style:em-dash",
                    "warn",
                    "fail",
                    f"report paragraph {number}: {em_dashes} em-dash punchlines — "
                    f"prefer plain sentences",
                    "report_md",
                )
            )
        hits = [m for m in voice.markers if m in paragraph]
        if hits:
            findings.append(
                Finding(
                    "report_md",
                    "style:metaphor",
                    "warn",
                    "fail",
                    f"report paragraph {number}: metaphor markers {hits} — state the "
                    f"technical fact directly",
                    "report_md",
                )
            )
        if _EN_TELL_WORDS.search(paragraph) and voice.enforces("en-tell"):
            findings.append(
                Finding(
                    "report_md",
                    "style:en-tell",
                    "warn",
                    "fail",
                    f"report paragraph {number}: AI-favored English wording — "
                    f"pick the concrete word",
                    "report_md",
                )
            )
    return findings


def validate_style(artifacts: dict[str, dict | None], report_md_text: str | None) -> list[Finding]:
    voice = (artifacts.get("brief") or {}).get("voice") or {}
    deck_voice = VoiceConfig(voice, voice.get("deck"))
    report_voice = VoiceConfig(voice, voice.get("report"))
    deck = artifacts.get("deck_plan") or {}
    findings: list[Finding] = []

    def forbidden_words(medium_voice: VoiceConfig, medium: str) -> None:
        for word in medium_voice.extra_forbidden:
            if medium == "deck":
                targets = [
                    (page["id"], element, text)
                    for page in deck.get("deck", {}).get("pages", [])
                    for element, text in _page_texts(page)
                ]
            else:
                targets = [
                    (f"report paragraph {number}", "body", paragraph.strip())
                    for number, paragraph in enumerate((report_md_text or "").split("\n\n"), 1)
                ]
            for page_id, element, text in targets:
                if word in text:
                    findings.append(
                        Finding(
                            "deck_plan" if medium == "deck" else "report_md",
                            "style:forbidden-word",
                            "warn",
                            "fail",
                            f"{page_id} {element}: '{word}' is forbidden by brief.voice.rules",
                            "deck_plan" if medium == "deck" else "report_md",
                        )
                    )

    forbidden_words(deck_voice, "deck")
    for page in deck.get("deck", {}).get("pages", []):
        for element, text in _page_texts(page):
            findings += lint_text(page["id"], element, text, deck_voice)
    if report_md_text:
        forbidden_words(report_voice, "report")
        findings += lint_report(report_md_text, report_voice)
    return findings

"""Readiness for human decisions; drafts may still be saved with open questions."""

from __future__ import annotations

from pathlib import Path

import yaml

from .artifacts import load_yaml

BRIEF_FIELDS = (
    "language",
    "audience",
    "objective",
    "delivery_context",
    "media",
    "takeaways",
    "constraints",
    "voice",
    "visual_materials",
    "appearance",
    "presentation",
)
STAGES = ("intake", "evidence", "brief", "narrative", "projection", "authoring", "qa", "deliver")


def has_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def question_errors(questions: list, stage: str) -> list[str]:
    errors = []
    if not isinstance(questions, list):
        return ["open_questions must be a list"]
    for q in questions:
        if not isinstance(q, dict) or not has_text(q.get("question")):
            errors.append("each open question needs question text")
            continue
        if has_text(q.get("answer")):
            continue
        status, due = q.get("status", "open"), q.get("due", "brief")
        if status == "not_applicable" and has_text(q.get("reason")):
            continue
        if (
            status == "deferred"
            and due in STAGES
            and stage in STAGES
            and STAGES.index(due) > STAGES.index(stage)
            and has_text(q.get("reason"))
        ):
            continue
        errors.append(f"unresolved question: {q['question']} (due: {due})")
    return errors


def brief_errors(brief: dict, stage: str = "brief") -> list[str]:
    from .appearance import applicable, policy_errors
    from .presentation_profile import applicable as has_presentation
    from .presentation_profile import policy_errors as presentation_errors

    errors = question_errors(brief.get("open_questions", []), stage) + policy_errors(brief)
    errors += presentation_errors(brief)
    if not has_text(brief.get("audience", {}).get("description")):
        errors.append("brief.audience.description cannot be blank")
    for field in ("language", "objective"):
        if not has_text(brief.get(field)):
            errors.append(f"brief.{field} cannot be blank")
    if any(not has_text(item) for item in brief.get("takeaways", [])):
        errors.append("brief.takeaways cannot contain blank entries")
    alignment = brief.get("alignment")
    if not isinstance(alignment, dict):
        return errors + ["brief.alignment must record the disposition of every contract field"]
    for field in BRIEF_FIELDS:
        if field == "appearance" and not applicable(brief):
            continue
        if field == "presentation" and not has_presentation(brief):
            continue
        entry = alignment.get(field)
        if not isinstance(entry, dict):
            errors.append(f"alignment.{field} is missing")
            continue
        status, source = entry.get("status"), entry.get("source")
        if source not in {"user", "material", "inference", "default"}:
            errors.append(f"alignment.{field} needs source: user/material/inference/default")
        if not isinstance(entry.get("basis"), str) or not entry["basis"].strip():
            errors.append(f"alignment.{field} needs a nonempty basis")
        if status in {"provided", "confirmed", "delegated"} and source != "user":
            errors.append(f"alignment.{field}: {status} requires a user basis")
        if status == "not_applicable":
            if field in {"language", "audience", "objective", "media", "takeaways"}:
                errors.append(f"alignment.{field} cannot be not_applicable")
            if field in brief and brief[field] not in (None, "", {}, []):
                errors.append(f"alignment.{field}: not_applicable conflicts with a value")
            continue
        if status == "deferred":
            due = entry.get("due")
            if (
                field != "visual_materials"
                or due not in STAGES
                or STAGES.index(due) <= STAGES.index(stage)
            ):
                errors.append(f"alignment.{field}: deferred decision is due or cannot be deferred")
            continue
        if status not in {"provided", "confirmed", "delegated", "proposed"}:
            errors.append(f"alignment.{field} is unresolved")
        if field not in brief or "value" not in entry or entry["value"] != brief[field]:
            errors.append(f"alignment.{field}.value must equal the owning brief field")
        if field in {"language", "audience", "objective", "media", "takeaways"} and not brief.get(
            field
        ):
            errors.append(f"brief.{field} cannot be empty")
    if has_presentation(brief):
        entry = alignment.get("presentation") or {}
        if entry.get("status") == "proposed":
            errors.append(
                "alignment.presentation cannot stay proposed: the density profile is a "
                "Gate 1 question — the user picks a profile, accepts the suggested "
                "default, or explicitly delegates it"
            )
    return errors


def narrative_errors(narrative: dict) -> list[str]:
    errors = []
    used = {c for beat in narrative.get("story", []) for c in beat.get("claims", [])}
    for claim in narrative.get("claims", []):
        if claim.get("status") in {"supported", "background"}:
            continue
        resolution = claim.get("resolution") or {}
        if not isinstance(resolution, dict):
            errors.append(f"claim {claim['id']}: resolution must be an object")
            continue
        action = resolution.get("action")
        if action not in {"qualify", "omit"} or not has_text(resolution.get("reason")):
            errors.append(f"claim {claim['id']}: decide how to qualify or omit the uncertainty")
        if action == "qualify" and not has_text(resolution.get("boundary")):
            errors.append(f"claim {claim['id']}: qualification needs an explicit boundary")
        if action == "omit" and claim["id"] in used:
            errors.append(f"claim {claim['id']}: omitted claim still used in the story")
    return errors


def coverage_errors(root: Path) -> list[str]:
    path = root / "evidence/coverage.yaml"
    if not path.is_file():
        return ["evidence/coverage.yaml is missing; account for read/partial/unread sources"]
    try:
        data = load_yaml(path)
    except (OSError, yaml.YAMLError):
        return ["evidence/coverage.yaml is unreadable or invalid YAML; fix it before acceptance"]
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        return ["coverage must contain sources: [{file, status, locator, reason}]"]
    errors, seen = [], set()
    for row in data["sources"]:
        if not isinstance(row, dict) or not isinstance(row.get("file"), str):
            errors.append("invalid coverage row")
            continue
        rel = row["file"]
        source = (root / rel).resolve()
        if not source.is_relative_to((root / "sources").resolve()) or not source.is_file():
            errors.append(f"coverage points outside sources or to a missing file: {rel}")
        if rel in seen:
            errors.append(f"duplicate coverage file: {rel}")
        seen.add(rel)
        if row.get("status") not in ("read", "partial", "unread"):
            errors.append(f"invalid coverage status: {rel}")
        required = "locator" if row.get("status") == "read" else "reason"
        if not has_text(row.get(required)):
            errors.append(f"coverage {rel} needs {required}")
    actual = {p.relative_to(root).as_posix() for p in (root / "sources").rglob("*") if p.is_file()}
    errors += [f"source has no coverage disposition: {rel}" for rel in sorted(actual - seen)]
    return errors

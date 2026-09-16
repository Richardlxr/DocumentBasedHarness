"""Version-bound dialogue receipts. This is an audit protocol, not user authentication."""

from __future__ import annotations

import json
from copy import deepcopy

import yaml

from .artifacts import load_yaml
from .contracts import required_artifacts
from .decision_checks import (
    brief_errors,
    coverage_errors,
    has_text,
    narrative_errors,
    question_errors,
)
from .lineage import hash_bytes, hash_file
from .manifest import Manifest, RunError, now_iso, upstream_chain

TARGETS = (
    "brief",
    "narrative",
    "deck_outline",
    "deck_appearance",
    "report_outline",
    "deck_detail",
    "report_detail",
    "delivery",
)
MODES = ("checkpoints", "collaborative", "delegated")
ARTIFACT = {
    "brief": "brief",
    "narrative": "narrative",
    "deck_outline": "deck_plan",
    "deck_appearance": "deck_plan",
    "report_outline": "report_plan",
    "deck_detail": "deck_plan",
    "report_detail": "report_plan",
}


def digest(value) -> str:
    return hash_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def state(manifest: Manifest) -> dict:
    return manifest.data.setdefault(
        "interaction", {"version": 1, "mode": "checkpoints", "requests": []}
    )


def read(manifest: Manifest, key: str) -> dict:
    data = load_yaml(manifest.artifact_path(key))
    if not isinstance(data, dict):
        raise RunError(f"{key} must be an object")
    return data


def intake(manifest: Manifest, data: dict) -> None:
    if not isinstance(data, dict) or any(
        not isinstance(data.get(k), str) or not data[k].strip()
        for k in ("goal", "source_scope", "basis")
    ):
        raise RunError("intake requires nonempty goal, source_scope and basis")
    if not isinstance(data.get("open_questions", []), list):
        raise RunError("intake.open_questions must be a list")
    if any(
        not isinstance(q, dict) or not has_text(q.get("question"))
        for q in data.get("open_questions", [])
    ):
        raise RunError("intake.open_questions entries need nonempty question text")
    s = state(manifest)
    s["intake"] = deepcopy(data)
    manifest.save()


def set_mode(manifest: Manifest, mode: str, reply: str, source: str) -> None:
    if mode not in MODES or not reply.strip() or not source.strip():
        raise RunError("mode changes need a mode, user reply and source")
    s = state(manifest)
    s["mode"] = mode
    s.setdefault("mode_history", []).append(
        {"mode": mode, "reply": reply, "source": source, "at": now_iso()}
    )
    if mode != "collaborative":
        for r in s["requests"]:
            if r["target"].endswith("detail") and r["state"] == "awaiting_user":
                r.update(state="superseded", reason="user changed refinement mode")
    manifest.save()


def _brief_view(brief: dict) -> dict:
    """Brief view carries the resolved density profile, so the Gate 1 density
    question quotes concrete budgets instead of a silent default."""
    from .presentation_profile import applicable, resolve_profile

    if not applicable(brief):
        return brief
    try:
        profile = resolve_profile(brief)
    except ValueError:
        return brief  # malformed presentation config surfaces via policy_errors blockers
    effective = {
        key: profile[key]
        for key in (
            "profile",
            "label",
            "setting",
            "selection",
            "text_budget",
            "substantive_blocks",
        )
        if key in profile
    }
    return {**brief, "presentation_effective": effective}


def _page_carrier(page: dict) -> str:
    visual = page.get("visual") or {}
    for key, carrier in (
        ("chart", "chart"),
        ("table", "table"),
        ("diagram", "diagram"),
        ("asset_refs", "image"),
    ):
        if visual.get(key):
            return carrier
    return "text"


def view(manifest: Manifest, target: str, node: str | None = None) -> dict:
    if target not in TARGETS:
        raise RunError(f"unknown decision target: {target}")
    if target == "brief":
        return _brief_view(read(manifest, target))
    if target == "narrative":
        return read(manifest, target)
    if target == "deck_appearance":
        from .appearance import view as appearance_view

        if node:
            raise RunError("appearance review does not take --node")
        return appearance_view(manifest)
    if target == "delivery":
        from .qa import reader_receipt

        review = manifest.root / "qa/model-findings.yaml"
        return {
            **manifest.review_snapshot(),
            "review_hash": hash_file(review) if review.is_file() else None,
            "reader_test": reader_receipt(manifest, load_yaml(review))
            if review.is_file()
            else None,
        }
    plan = read(manifest, ARTIFACT[target])
    deck = target.startswith("deck")
    nodes = plan.get("deck", {}).get("pages", []) if deck else plan.get("sections", [])
    if target.endswith("detail"):
        matches = [n for n in nodes if n["id"] == node]
        if len(matches) != 1:
            raise RunError("detail review requires an existing, unique --node")
        return matches[0]
    if node:
        raise RunError("--node is only valid for detail reviews")
    fields = (
        ("id", "page_role", "title", "beat", "beats", "merge_rationale")
        if deck
        else ("id", "heading", "beats", "merge_rationale")
    )
    if deck:
        summary: dict[str, int] = {}
        nodes_out = []
        for page in nodes:
            carrier = _page_carrier(page)
            summary[carrier] = summary.get(carrier, 0) + 1
            row = {key: page[key] for key in fields if key in page}
            row["carrier"] = carrier
            nodes_out.append(row)
        return {
            "title": plan.get("deck", {}).get("title"),
            "nodes": nodes_out,
            "carrier_summary": summary,
            "omissions": plan.get("omissions", []),
        }
    return {
        "title": plan.get("title"),
        "nodes": [{key: n[key] for key in fields if key in n} for n in nodes],
        "omissions": plan.get("omissions", []),
    }


def binding(manifest: Manifest, target: str, node: str | None = None) -> dict:
    if target == "deck_appearance":
        from .appearance import signature

        return {"run": str(manifest.root.resolve()), "appearance": signature(manifest)}
    parents = (
        [] if target == "brief" else ["brief"] if target == "narrative" else ["brief", "narrative"]
    )
    key = ARTIFACT.get(target)
    upstream = upstream_chain(key) - {key} if key else set()
    coverage = manifest.root / "evidence/coverage.yaml"
    return {
        "run": str(manifest.root.resolve()),
        "view": digest(view(manifest, target, node)),
        "artifact": manifest._current_hash(target) if target in {"brief", "narrative"} else None,
        "upstream": {k: manifest._current_hash(k) for k in sorted(upstream)},
        "sources": manifest._current_hash("sources"),
        "coverage": hash_file(coverage) if coverage.is_file() else None,
        "intake": digest(state(manifest).get("intake")),
        "parents": {k: manifest.data["gates"][k].get("request_id") for k in parents},
    }


def latest(manifest: Manifest, target: str, node: str | None = None) -> dict | None:
    return next(
        (
            r
            for r in reversed(state(manifest)["requests"])
            if r["target"] == target and r.get("node") == node
        ),
        None,
    )


def valid(manifest: Manifest, target: str, node: str | None = None) -> bool:
    r = latest(manifest, target, node)
    if not r or r["state"] not in {"accepted", "delegated"}:
        return False
    try:
        return r["binding"] == binding(manifest, target, node)
    except (RunError, OSError, KeyError, ValueError, yaml.YAMLError):
        return False


def readiness(manifest: Manifest, target: str) -> list[str]:
    if not state(manifest).get("intake"):
        return ["record the lightweight intake with `comh intake <file>` first"]
    stage = {"brief": "brief", "narrative": "narrative", "delivery": "deliver"}.get(
        target, "projection"
    )
    if target.endswith("detail"):
        stage = "authoring"
    errors = brief_errors(read(manifest, "brief"), stage)
    questions = {
        q.get("question"): q
        for q in state(manifest)["intake"].get("open_questions", [])
        if isinstance(q, dict)
    }
    questions.update(
        {q.get("question"): q for q in read(manifest, "brief").get("open_questions", [])}
    )
    errors += question_errors(list(questions.values()), stage)
    errors += coverage_errors(manifest.root)
    if target == "deck_appearance":
        from .appearance import preview_errors

        errors += preview_errors(manifest)
    if target != "brief":
        errors += narrative_errors(read(manifest, "narrative"))
    return list(dict.fromkeys(errors))


def require_parents(manifest: Manifest, target: str) -> None:
    if target != "brief":
        manifest.require_gate("brief")
    if target not in {"brief", "narrative"}:
        manifest.require_gate("narrative")
    if target.endswith("detail"):
        require_outline(manifest, "deck_plan" if target.startswith("deck") else "report_plan")
    if target == "deck_appearance":
        require_outline(manifest, "deck_plan")
    if target == "deck_detail":
        from .appearance import require_appearance

        require_appearance(manifest)


def present(manifest: Manifest, target: str, node: str | None = None, summary: str = "") -> dict:
    require_parents(manifest, target)
    if target in ARTIFACT:
        manifest.require_fresh(ARTIFACT[target])
    if not state(manifest).get("intake"):
        raise RunError("record intake before presenting a decision")
    current_binding = binding(manifest, target, node)
    old = latest(manifest, target, node)
    if (
        old
        and old["binding"] == current_binding
        and old.get("summary", "") == summary
        and old["state"] in {"awaiting_user", "accepted", "delegated"}
        and (
            target != "deck_appearance"
            or old["state"] != "awaiting_user"
            or old["view"]["sample"] == view(manifest, target)["sample"]
        )
    ):
        return old
    pending = [r for r in state(manifest)["requests"] if r["state"] == "awaiting_user"]
    obsolete = []
    for r in pending:
        try:
            current = r["binding"] == binding(manifest, r["target"], r.get("node"))
        except (RunError, OSError, KeyError, ValueError, yaml.YAMLError):
            current = False
        if not current:
            obsolete.append(r)
            continue
        if r["target"] != target or r.get("node") != node:
            raise RunError(
                f"request {r['id']} awaits the user; respond before another presentation"
            )
    for r in pending:
        r.update(
            state="superseded",
            reason="proposal or upstream changed" if r in obsolete else "new presentation",
        )
    requests = state(manifest)["requests"]
    request = {
        "id": f"D{len(requests) + 1:04d}",
        "target": target,
        "node": node,
        "state": "awaiting_user",
        "binding": current_binding,
        "view": view(manifest, target, node),
        "summary": summary,
        "summary_hash": digest(summary),
        "presented_at": now_iso(),
        "recording": "agent_attested",
        "blockers": readiness(manifest, target),
    }
    requests.append(request)
    manifest.save()
    return request


def respond(manifest: Manifest, request_id: str, decision: str, reply: str, source: str) -> dict:
    if (
        decision not in {"accepted", "changes_requested", "delegated"}
        or not reply.strip()
        or not source.strip()
    ):
        raise RunError(
            "decision requires accepted/changes_requested/delegated, actual user reply and source"
        )
    request = next((r for r in state(manifest)["requests"] if r["id"] == request_id), None)
    if request is None:
        raise RunError(f"unknown request {request_id}")
    response = {"decision": decision, "reply": reply, "source": source}
    if request["state"] != "awaiting_user":
        if request.get("response") == response:
            return request  # idempotent acknowledgement; never updates a newer request
        raise RunError("request already answered or superseded")
    target, node = request["target"], request.get("node")
    if decision != "changes_requested":
        require_parents(manifest, target)
        if request["binding"] != binding(manifest, target, node):
            raise RunError("proposal changed since presentation; present the current version again")
        if (
            target == "deck_appearance"
            and request["view"]["sample"] != view(manifest, target)["sample"]
        ):
            raise RunError("appearance sample changed; present the current preview again")
        if target in ARTIFACT:
            manifest.require_fresh(ARTIFACT[target])
        if decision == "delegated" and target in {"brief", "narrative", "delivery"}:
            raise RunError("brief/narrative/delivery need acceptance; delegation cannot skip them")
        errors = readiness(manifest, target)
        if errors:
            raise RunError("cannot accept: " + "; ".join(errors))
    request.update(state=decision, response=response, responded_at=now_iso())
    if target in {"brief", "narrative"}:
        manifest.data["gates"][target] = {
            "confirmed": decision == "accepted",
            "at": now_iso(),
            "hash": manifest._current_hash(target),
            "request_id": request_id,
        }
    manifest.save()
    return request


def require_outline(manifest: Manifest, artifact: str, *, details: bool = False) -> None:
    if details and read(manifest, artifact).get("draft", False):
        raise RunError(f"{artifact} is a draft; finish authoring before rendering or saving prose")
    target = "deck_outline" if artifact == "deck_plan" else "report_outline"
    if not valid(manifest, target):
        raise RunError(f"{target} needs a current accepted or delegated presentation")
    if (
        details
        and state(manifest)["mode"] == "collaborative"
        and latest(manifest, target)["state"] != "delegated"
    ):
        plan = read(manifest, artifact)
        nodes = plan["deck"]["pages"] if artifact == "deck_plan" else plan["sections"]
        detail = target.replace("outline", "detail")
        missing = [n["id"] for n in nodes if not valid(manifest, detail, n["id"])]
        if missing:
            raise RunError(
                f"collaborative refinement needs {detail} decisions: {', '.join(missing)}"
            )


def accepted_receipts(manifest: Manifest) -> dict:
    """Only decisions governing selected content; pending chat does not dirty builds."""
    result = {"intake": state(manifest).get("intake"), "mode": state(manifest)["mode"]}
    keys = required_artifacts(manifest.brief())
    for target in TARGETS[:-1]:
        if ARTIFACT[target] not in keys:
            continue
        nodes = {r.get("node") for r in state(manifest)["requests"] if r["target"] == target}
        for node in sorted(nodes, key=lambda n: n or ""):
            if valid(manifest, target, node):
                last = latest(manifest, target, node)
                result[f"{target}:{node}"] = {
                    k: last[k] for k in ("id", "state", "binding", "response")
                }
    return deepcopy(result)

"""Appearance decisions are separate from narrative and outline acceptance."""

from __future__ import annotations

import json
from dataclasses import fields

import yaml

from .artifacts import load_yaml
from .lineage import hash_bytes, hash_file
from .manifest import Manifest, RunError


def applicable(brief: dict) -> bool:
    return any(m.get("medium") == "pptx" for m in brief.get("media", []))


def policy_errors(brief: dict) -> list[str]:
    if not applicable(brief):
        return []
    policy = brief.get("appearance")
    if not isinstance(policy, dict):
        return ["brief.appearance must state template intent and sample-review policy"]
    errors = []
    if policy.get("selection") not in {"default", "specified", "deferred", "delegated"}:
        errors.append("appearance.selection needs default/specified/deferred/delegated")
    if policy.get("review", "sample") not in {"sample", "delegated"}:
        errors.append("appearance.review needs sample/delegated")
    if policy.get("selection") == "specified" and not policy.get("reference"):
        errors.append("appearance.reference must identify the specified profile or theme")
    return errors


def _deck(manifest: Manifest) -> dict:
    path = manifest.artifact_path("deck_plan")
    return (load_yaml(path) or {}).get("deck", {}) if path.is_file() else {}


def selection_errors(manifest: Manifest) -> list[str]:
    if not applicable(manifest.brief()):
        return []
    policy = manifest.brief().get("appearance") or {}
    style = _deck(manifest).get("style") or {}
    if policy.get("selection") == "specified" and policy.get("reference") not in {
        style.get("pptx_style"),
        style.get("template"),
    }:
        return ["selected appearance differs from the brief; explicitly review this change"]
    return []


def needs_review(manifest: Manifest) -> bool:
    from .dialogue import latest, run_identity

    brief = manifest.brief()
    if not applicable(brief):
        return False
    # A user may reopen even a default/delegated style for review. A pending or
    # rejected current proposal cannot be bypassed by the original default policy.
    request = latest(manifest, "deck_appearance")
    if request and request.get("binding") == {
        "run": run_identity(manifest),
        "appearance": signature(manifest),
    }:
        return True
    policy = brief.get("appearance") or {}
    if selection_errors(manifest):
        return True
    if policy.get("review") == "delegated":
        return (
            policy.get("selection") == "deferred"
        )  # Explicit, Gate-1-accepted sample-review delegation, not outline delegation.
    deck = _deck(manifest)
    style = deck.get("style") or {}
    return bool(
        "pptx_style" in style
        or policy.get("selection") in {"deferred", "delegated"}
        or deck.get("appearance_review")
        or style.get("tokens_override")
        or (style.get("template") and policy.get("selection") != "specified")
    )


def specification(manifest: Manifest) -> dict:
    """Only appearance inputs. Content edits and no-wrap defect repairs do not change intent."""
    deck = _deck(manifest)
    style = deck.get("style") or {}
    result = {
        "policy": manifest.brief().get("appearance"),
        "selection": {
            k: style[k] for k in ("pptx_style", "template", "tokens_override") if k in style
        },
        "review": deck.get("appearance_review") or {},
        "changes_from_brief": selection_errors(manifest),
    }
    from .render.theme import resolve_style

    theme = resolve_style(style, run_root=manifest.root).theme
    # Bind the effective tokens, not unrelated theme files in the same registry.
    result["effective_theme"] = {
        f.name: list(v) if isinstance(v := getattr(theme, f.name), tuple) else v
        for f in fields(theme)
        if f.name != "notes"
    }
    if "pptx_style" in style:
        from .pptx_style import StyleError, load_style

        try:
            profile = load_style(manifest.root, style["pptx_style"])
        except StyleError as error:
            raise RunError(str(error)) from error
        result["native_style"] = {
            "name": profile.name,
            "source_sha256": profile.source_hash,
            "tokens": profile.tokens,
            "surfaces": [
                {"role": s.role, "slide": s.slide, "keep": s.keep, "tokens": s.tokens}
                for s in profile.surfaces
            ],
        }
    return result


def signature(manifest: Manifest) -> str:
    return hash_bytes(
        json.dumps(specification(manifest), ensure_ascii=False, sort_keys=True).encode()
    )


def preview_errors(manifest: Manifest) -> list[str]:
    output = manifest.root / ".workspace/preview-deck.pptx"
    report = manifest.root / ".workspace/preview-deck.yaml"
    hint = "render deck --preview before presenting the appearance sample"
    if not output.is_file() or not report.is_file():
        return [hint]
    try:
        data = load_yaml(report)
        if (
            not isinstance(data, dict)
            or data.get("appearance_signature") != signature(manifest)
            or data.get("output_sha256") != hash_file(output)
            or data.get("count", {}).get("error", 0)
            or any(f.get("verdict") == "fail" for f in data.get("findings", []))
        ):
            return ["appearance preview is stale, changed or failed; " + hint]
    except (OSError, yaml.YAMLError, RunError):
        return ["appearance preview cannot be verified; " + hint]
    return []


def view(manifest: Manifest) -> dict:
    output = manifest.root / ".workspace/preview-deck.pptx"
    return {
        **specification(manifest),
        "sample": {
            "path": output.relative_to(manifest.root).as_posix(),
            "sha256": hash_file(output) if output.is_file() else None,
        },
        "scope": (
            "Appearance only: backgrounds, branding/icons and typography; not outline or density."
        ),
    }


def require_appearance(manifest: Manifest) -> None:
    from .dialogue import valid

    errors = policy_errors(manifest.brief())
    if errors:
        raise RunError("; ".join(errors))
    if needs_review(manifest) and not valid(manifest, "deck_appearance"):
        raise RunError(
            "deck_appearance needs a current accepted/delegated sample; "
            "preview first, then present deck_appearance"
        )

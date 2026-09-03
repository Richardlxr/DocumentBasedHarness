"""Persistent, version-bound model reviews and render findings."""

from __future__ import annotations

from pathlib import Path

import yaml

from .artifacts import Finding
from .contracts import hard_constraints
from .decision_checks import has_text
from .lineage import hash_file
from .manifest import Manifest, RunError, now_iso

REVIEW_CHECKS = {"narrative", "audience", "reader", "style"}


def reader_receipt(manifest: Manifest, data: dict) -> dict:
    if not isinstance(data, dict):
        raise RunError("reader test record must be an object")
    reader = data.get("reader_test")
    if not isinstance(reader, dict) or any(
        not has_text(reader.get(k)) for k in ("output", "executor", "input_scope")
    ):
        raise RunError(
            "reader_test needs output, executor and input_scope; a checkbox is not output"
        )
    output = (manifest.root / reader["output"]).resolve()
    if not output.is_relative_to(manifest.root.resolve()) or not output.is_file():
        raise RunError("reader_test.output must be an existing file inside this run")
    if not output.read_bytes().strip():
        raise RunError("reader_test.output must contain the actual reader response")
    return {**reader, "hash": hash_file(output), "recording": "agent_attested"}


def read_report(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise RunError(f"cannot read QA report {path}: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        raise RunError(f"QA report {path} must contain a findings list")
    for entry in data["findings"]:
        if (
            not isinstance(entry, dict)
            or entry.get("severity") not in {"error", "warn", "info"}
            or not all(
                isinstance(entry.get(k), str) and entry[k].strip()
                for k in ("artifact", "check", "detail")
            )
            or entry.get("state", "open") not in {"open", "resolved", "waived"}
        ):
            raise RunError(f"invalid finding in QA report {path}")
        if entry.get("state") in {"resolved", "waived"} and not entry.get("reason"):
            raise RunError(f"resolved/waived findings need a reason in {path}")
        if entry.get("state") == "waived" and entry["severity"] == "error":
            raise RunError("error findings must be resolved, not waived")
    return data


def report_findings(data: dict) -> list[Finding]:
    return [
        Finding(
            e["artifact"],
            e["check"],
            e["severity"],
            e.get("verdict", "fail"),
            e["detail"],
            e.get("owning_artifact", e["artifact"]),
        )
        for e in data["findings"]
        if e.get("state", "open") == "open"
    ]


def preserve_legacy_review(root: Path) -> None:
    """Migrate hand-appended model findings before rewriting the aggregate."""
    aggregate, canonical = root / "qa/findings.yaml", root / "qa/model-findings.yaml"
    if not aggregate.is_file():
        return
    data = read_report(aggregate)
    old = read_report(canonical) if canonical.is_file() else {"findings": []}
    signatures = {(e["artifact"], e["check"], e["detail"]) for e in old["findings"]}
    new = [
        e
        for e in data["findings"]
        if e["check"].startswith("model:")
        and (e["artifact"], e["check"], e["detail"]) not in signatures
    ]
    if new:
        old["findings"].extend(new)
        old["inputs"] = None  # no evidence of which version was reviewed
        canonical.write_text(
            yaml.safe_dump(old, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )


def record_review(manifest: Manifest, source: Path) -> None:
    data = read_report(source)
    completed = data.get("completed_checks")
    if (
        not isinstance(completed, list)
        or not all(isinstance(c, str) for c in completed)
        or not set(completed) >= REVIEW_CHECKS
    ):
        raise RunError(f"review needs completed_checks: {', '.join(sorted(REVIEW_CHECKS))}")
    if any(not e["check"].startswith("model:") for e in data["findings"]):
        raise RunError("model review findings must use a 'model:' check prefix")
    checks = data.get("manual_constraints", [])
    if not isinstance(checks, list) or not all(
        isinstance(c, dict)
        and isinstance(c.get("id"), str)
        and c.get("verdict") in {"pass", "fail"}
        and isinstance(c.get("detail"), str)
        and c["detail"].strip()
        for c in checks
    ):
        raise RunError("manual_constraints needs {id, verdict: pass|fail, detail} entries")
    if len({c["id"] for c in checks}) != len(checks):
        raise RunError("duplicate manual constraint review IDs")
    data["reader_test"] = reader_receipt(manifest, data)
    data.update(version=1, reviewed_at=now_iso(), inputs=manifest.review_snapshot())
    output = manifest.root / "qa/model-findings.yaml"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    # The canonical record supersedes the former aggregate's model entries.
    aggregate = manifest.root / "qa/findings.yaml"
    if aggregate.is_file():
        old = read_report(aggregate)
        old["findings"] = [
            e for e in old["findings"] if not e["check"].startswith(("model:", "qa:"))
        ]
        old["count"] = {
            s: sum(e["severity"] == s for e in old["findings"]) for s in ("error", "warn", "info")
        }
        aggregate.write_text(
            yaml.safe_dump(old, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )


def review_findings(manifest: Manifest, *, required: bool = False) -> list[Finding]:
    path = manifest.root / "qa/model-findings.yaml"
    if not path.is_file():
        return (
            [
                Finding(
                    "qa",
                    "qa:review",
                    "error",
                    "fail",
                    "current model review missing; run `comh review <file>`",
                )
            ]
            if required
            else []
        )
    try:
        data = read_report(path)
    except RunError as error:
        return [Finding("qa", "qa:review", "error", "fail", str(error))]
    findings = report_findings(data)
    if data.get("inputs") != manifest.review_snapshot():
        findings.append(
            Finding(
                "qa",
                "qa:review",
                "error" if required else "warn",
                "fail",
                "model review is stale/unbound; recheck outputs and run `comh review <file>`",
            )
        )
    if required:
        try:
            if data.get("reader_test") != reader_receipt(manifest, data):
                raise RunError("reader output changed after review; rerun the reader check")
        except RunError as error:
            findings.append(Finding("qa", "qa:reader", "error", "fail", str(error)))
        completed = data.get("completed_checks") or []
        if not set(completed) >= REVIEW_CHECKS:
            findings.append(
                Finding(
                    "qa", "qa:review", "error", "fail", "model review is missing required checks"
                )
            )
        reviewed = {c["id"]: c for c in data.get("manual_constraints", [])}
        for constraint in hard_constraints(manifest.brief()):
            if constraint["check"] != "manual":
                continue
            entry = reviewed.get(constraint["id"], {})
            if entry.get("verdict") != "pass" or not entry.get("detail"):
                findings.append(
                    Finding(
                        "brief",
                        "qa:manual-constraint",
                        "error",
                        "fail",
                        f"hard constraint '{constraint['id']}' needs a passing review: "
                        f"{constraint['text']}",
                    )
                )
    return findings


def render_findings(manifest: Manifest) -> list[Finding]:
    findings = []
    filenames = {
        "deck": "render-deck.yaml",
        "deck_html": "render-deck-html.yaml",
        "report_docx": "render-report.yaml",
    }
    for key in manifest.output_selection() - {"report_md"}:
        path = manifest.root / "qa" / filenames[key]
        if path.is_file():
            try:
                findings.extend(report_findings(read_report(path)))
            except RunError as error:
                findings.append(Finding("qa", "qa:render", "error", "fail", str(error)))
    return findings

"""comh — the communication harness CLI.

Commands mirror the artifact lifecycle:

    init-run <path>      scaffold a run workspace
    status               live state: artifacts (drift/staleness) + gates + delivery
    save <artifact>      record "produced from current upstream" (hash snapshot)
    confirm <gate>       user confirms brief / narrative (hard gate)
    validate [target]    schema + cross-artifact checks → qa/findings.yaml
    render <target>      deck → build/deck.pptx; report → build/report.docx
    evidence-pack ...    ID-chain slice for one page/beat/section (repair-loop QA)
    theme-from-pptx ...  extract a brand theme from a template .pptx
    deliver              record user acceptance of the build outputs (final gate)

Stage guards are enforced here, not by prompt discipline: downstream commands
refuse to run when an upstream gate is missing or invalidated.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from .artifacts import ARTIFACT_KEYS, Finding, load_artifact, validate_schema
from .contracts import forbids_dark, required_artifacts
from .evidence_pack import build_pack, format_pack
from .manifest import (
    DERIVATION,
    GATE_OF_ARTIFACT,
    Manifest,
    RunError,
    find_run_root,
    upstream_chain,
)
from .qa import preserve_legacy_review, record_review, render_findings, review_findings
from .render import render_deck, render_html_deck, render_report
from .scaffold import init_run
from .validate import run_all, write_findings


def _resolve_run(args: argparse.Namespace) -> Path:
    root = find_run_root(Path(args.run).resolve() if args.run else Path.cwd())
    if root is None:
        raise RunError("not inside a run workspace (no run.yaml); use --run or cd into runs/<name>")
    return root


def _upstream_chain(key: str) -> set[str]:
    return upstream_chain(key)


def _require_validated(manifest: Manifest, keys: set[str], action: str) -> None:
    """Hard-chain `comh validate`: an operation's inputs must be error-free.

    Findings outside ``keys`` never block — a broken sibling projection does
    not stop the deck, and a stale downstream artifact does not block an
    upstream save (it will be re-derived anyway).
    """
    blocking = [f for f in run_all(manifest.root, keys=keys) if f.severity == "error"]
    if blocking:
        for finding in blocking:
            print(f"  ✗ {finding.artifact}/{finding.check}: {finding.detail}", file=sys.stderr)
        artifacts = ", ".join(sorted({f.artifact for f in blocking}))
        raise RunError(
            f"cannot {action}: validation error(s) in {artifacts}; run `comh validate all`"
        )


def cmd_init_run(args: argparse.Namespace) -> int:
    target = init_run(Path(args.path), args.name, preset=args.preset)
    print(f"initialized run workspace: {target}")
    print("next: drop source material into sources/, then follow stages/evidence.md")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    manifest = Manifest.load(_resolve_run(args))
    name = manifest.data["name"]
    print(f"run: {name}  ({manifest.root})")
    print("artifacts:")
    for key in ARTIFACT_KEYS + ("report_md",):
        state = manifest.artifact_state(key)
        marker = {
            "absent": "·",
            "unsaved": "~",
            "modified": "!",
            "stale": "!",
            "confirmed": "✓",
            "saved": "✓",
        }[state.state]
        print(f"  [{marker}] {key:<12} {state.state:<10} {state.detail}")
    print("gates:")
    for gate in manifest.data["gates"]:
        record = manifest.data["gates"][gate]
        if manifest.gate_valid(gate):
            print(f"  [✓] {gate:<10} confirmed at {record['at']}")
        elif record.get("confirmed"):
            print(f"  [!] {gate:<10} invalidated: file changed after confirmation")
        else:
            print(f"  [·] {gate:<10} not confirmed")
    state, record = manifest.delivery_state()
    if state == "none":
        print("delivery:  [·] not accepted")
    elif state == "accepted":
        print(f"delivery:  [✓] accepted at {record['accepted_at']}")
    else:
        print(
            f"delivery:  [!] invalidated: build outputs changed since "
            f"{record['accepted_at']}; re-render and re-accept (`comh deliver`)"
        )
    return 0


def cmd_save(args: argparse.Namespace) -> int:
    manifest = Manifest.load(_resolve_run(args))
    key = args.artifact
    if key not in manifest.data["artifacts"]:
        raise RunError(f"unknown artifact '{key}' (known: {', '.join(manifest.data['artifacts'])})")
    # Guards: an artifact may only be saved from a valid upstream state.
    for upstream in DERIVATION[key]:
        if upstream == "sources":
            continue
        if upstream in manifest.data["gates"]:
            manifest.require_gate(upstream)
        else:
            manifest.require_fresh(upstream)
    # Schema must pass before the save is recorded (report_md is prose, not schema'd).
    if key != "report_md":
        data, findings = load_artifact(manifest.root, key)
        errors = [f for f in findings if f.severity == "error"]
        if data is None or errors:
            for finding in errors:
                print(f"schema error: {finding.detail}", file=sys.stderr)
            raise RunError(f"cannot save '{key}': schema validation failed")
    # Cross-artifact validators are a hard prerequisite too: the artifact and
    # its upstream chain must be error-free at save time.
    _require_validated(manifest, _upstream_chain(key), f"save '{key}'")
    manifest.mark_saved(key)
    print(f"saved '{key}' (upstream snapshot: {', '.join(DERIVATION[key])})")
    gate = GATE_OF_ARTIFACT.get(key)
    if gate and not manifest.gate_valid(gate):
        print(f"note: gate '{key}' needs user confirmation → `comh confirm {key}`")
    return 0


def cmd_confirm(args: argparse.Namespace) -> int:
    manifest = Manifest.load(_resolve_run(args))
    gate = args.gate
    # A gate confirms saved, fresh, error-free content — never a hand-edited
    # file that skipped `comh save` (and its checks).
    manifest.require_fresh(gate)
    keys = {"evidence", "brief"} if gate == "brief" else {"evidence", "brief", "narrative"}
    _require_validated(manifest, keys, f"confirm gate '{gate}'")
    # A gate may only be confirmed when its upstream gate (if any) is valid.
    if gate == "narrative":
        manifest.require_gate("brief")
    manifest.confirm_gate(gate)
    record = manifest.data["gates"][gate]
    print(f"gate '{gate}' confirmed at {record['at']}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    run_root = _resolve_run(args)
    if args.target != "all" and args.target not in DERIVATION:
        raise RunError(f"unknown validation target '{args.target}'")
    keys = None if args.target == "all" else _upstream_chain(args.target)
    findings = run_all(run_root, keys=keys)
    if args.target == "all":
        preserve_legacy_review(run_root)
        manifest = Manifest.load(run_root)
        findings += review_findings(manifest)
        findings += render_findings(manifest)
    path = write_findings(run_root, findings)
    errors = [f for f in findings if f.severity == "error"]
    warns = [f for f in findings if f.severity == "warn"]
    for finding in findings:
        marker = {"error": "✗", "warn": "△", "info": "·"}[finding.severity]
        owner = ""
        if finding.owning_artifact != finding.artifact:
            owner = f" → fix: {finding.owning_artifact}"
        print(f"  [{marker}] {finding.artifact}/{finding.check}: {finding.detail}{owner}")
    print(f"findings: {len(errors)} error(s), {len(warns)} warn(s) → {path}")
    return 1 if errors else 0


def cmd_render(args: argparse.Namespace) -> int:
    manifest = Manifest.load(_resolve_run(args))
    run_root = manifest.root
    key = {"deck": "deck", "deck-html": "deck_html", "report": "report_docx"}[args.target]
    artifact = "report_md" if key == "report_docx" else "deck_plan"
    manifest.require_gate("brief")
    manifest.require_gate("narrative")
    manifest.require_fresh(artifact)
    _require_validated(manifest, _upstream_chain(artifact), f"render {args.target}")
    inputs = manifest.begin_build(key)
    output = manifest.output_path(key)
    report_path = run_root / "qa" / f"render-{args.target}.yaml"
    metadata = {"output": str(output), "inputs": inputs}
    findings = []
    if key == "report_docx":
        render_report(manifest.artifact_path("report_md"), run_root / "templates/base.docx", output)
    else:
        plan, _ = load_artifact(run_root, "deck_plan")
        evidence, _ = load_artifact(run_root, "evidence")
        brief = manifest.brief()
        renderer = render_html_deck if key == "deck_html" else render_deck
        result = renderer(
            plan,
            run_root,
            output,
            language=brief.get("language", "en"),
            evidence=evidence,
            allow_dark=not forbids_dark(brief),
        )
        if key == "deck_html":
            _headless_layout_check(output, result)
        findings = result.findings
        metadata.update(theme=result.theme, transition=result.transition)
    metadata.update(
        count={s: sum(f.severity == s for f in findings) for s in ("error", "warn", "info")},
        findings=[f.as_dict() for f in findings],
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    success = not any(f.severity == "error" for f in findings)
    manifest.record_build(key, inputs, report_path, success)
    for finding in findings:
        print(f"  [{'✗' if finding.severity == 'error' else '△'}] render: {finding.detail}")
    print(f"rendered {args.target} → {output}; render report → {report_path}")
    return 0 if success else 1


def _headless_layout_check(html_path: Path, result) -> None:
    """Run the embedded layout guard in headless Chrome and fold its findings
    into the render report — the HTML twin of the pptx geometry gate."""
    import json as json_module
    import re as re_module
    import subprocess as subprocess_module

    from .render.icons import _chrome

    chrome = _chrome()
    if chrome is None:
        result.findings.append(
            Finding(
                "deck_plan",
                "layout",
                "warn",
                "fail",
                "[html] layout check skipped: headless Chrome not found (set COMH_CHROME); "
                "geometry findings are not guaranteed for this output",
                "deck_plan",
            )
        )
        return
    completed = subprocess_module.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--virtual-time-budget=4000",
            "--window-size=1600,900",
            "--dump-dom",
            html_path.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    match = re_module.search(r'data-layout-findings="(.*?)"', completed.stdout or "")
    if not match:
        result.findings.append(
            Finding(
                "deck_plan",
                "layout",
                "warn",
                "fail",
                "[html] layout check produced no read-back (guard script did not run)",
                "deck_plan",
            )
        )
        return
    import html as html_module

    try:
        issues = json_module.loads(
            html_module.unescape(match.group(1)).encode().decode("unicode_escape")
        )
    except (ValueError, UnicodeDecodeError):
        result.findings.append(
            Finding(
                "deck_plan",
                "layout",
                "warn",
                "fail",
                "[html] layout check read-back could not be parsed",
                "deck_plan",
            )
        )
        return
    for issue in issues[:20]:
        result.findings.append(
            Finding("deck_plan", "layout", "warn", "fail", f"[html] {issue}", "deck_plan")
        )


def cmd_theme_from_pptx(args: argparse.Namespace) -> int:
    from .render.theme import theme_from_pptx

    source = Path(args.pptx)
    if not source.is_file():
        raise RunError(f"template not found: {source}")
    run_root = _resolve_run(args)
    output = theme_from_pptx(source, args.name, run_root)
    print(f"extracted theme '{args.name}' → {output}")
    print(f"use it: deck.style.template: {args.name}")
    return 0


def cmd_evidence_pack(args: argparse.Namespace) -> int:
    run_root = _resolve_run(args)
    pack = build_pack(run_root, args.artifact, args.id)
    print(format_pack(pack), end="")
    return 0


def cmd_check_schema(args: argparse.Namespace) -> int:
    data = yaml.safe_load(Path(args.file).read_text(encoding="utf-8"))
    name = Path(args.file).stem
    errors = validate_schema(name, data)
    for error in errors:
        print(f"  ✗ {error}")
    print(f"{name}: {'OK' if not errors else f'{len(errors)} schema error(s)'}")
    return 1 if errors else 0


def _require_deliverables(manifest: Manifest) -> set[str]:
    keys = required_artifacts(manifest.brief())
    _require_validated(manifest, keys, "prepare delivery")
    manifest.require_gate("brief")
    manifest.require_gate("narrative")
    for key in keys:
        manifest.require_fresh(key)
    outputs = manifest.output_selection()
    if not outputs:
        raise RunError("no supported outputs selected in brief.media")
    for key in outputs:
        if key == "report_md":
            manifest.require_fresh(key)
        else:
            manifest.require_build(key)
    return outputs


def cmd_review(args: argparse.Namespace) -> int:
    """Record completed judgment checks against the current, built deliverables."""
    manifest = Manifest.load(_resolve_run(args))
    _require_deliverables(manifest)
    record_review(manifest, Path(args.file))
    print("review recorded against current outputs; `comh deliver` checks unresolved errors")
    return 0


def cmd_deliver(args: argparse.Namespace) -> int:
    manifest = Manifest.load(_resolve_run(args))
    _require_deliverables(manifest)
    preserve_legacy_review(manifest.root)
    findings = review_findings(manifest, required=True) + render_findings(manifest)
    errors = [f for f in findings if f.severity == "error"]
    if errors:
        for finding in errors:
            print(f"  ✗ {finding.check}: {finding.detail}", file=sys.stderr)
        raise RunError("cannot deliver: unresolved or stale QA; review current outputs")
    record = manifest.record_delivery(note=args.note)
    print(f"delivery recorded at {record['accepted_at']}: {', '.join(record['outputs'])}")
    print("acceptance pins current inputs, builds, canonical Markdown and review")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="comh", description=__doc__.splitlines()[0])
    parser.add_argument("--run", help="path to a run workspace (default: nearest run.yaml)")
    # Each subcommand also accepts --run (after the subcommand). SUPPRESS keeps the
    # subparser from clobbering a value parsed before the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--run", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common], help=help_)

    p = add("init-run", "scaffold a run workspace")
    p.add_argument("path")
    p.add_argument("--name")
    p.add_argument("--preset", default="standard", help="docx template preset")
    p.set_defaults(func=cmd_init_run)

    p = add("status", "show artifact states and gates")
    p.set_defaults(func=cmd_status)

    p = add("save", "record an artifact as produced from current upstream")
    p.add_argument("artifact", choices=[*DERIVATION])
    p.set_defaults(func=cmd_save)

    p = add("confirm", "user confirms a gate (brief | narrative)")
    p.add_argument("gate", choices=["brief", "narrative"])
    p.set_defaults(func=cmd_confirm)

    p = add("validate", "schema + cross-artifact checks")
    p.add_argument("target", nargs="?", default="all")
    p.set_defaults(func=cmd_validate)

    p = add("render", "render a final artifact")
    p.add_argument("target", choices=["deck", "report", "deck-html"])
    p.set_defaults(func=cmd_render)

    p = add("evidence-pack", "ID-chain slice for a deck page / report section / beat")
    p.add_argument("artifact", choices=["deck", "report", "narrative"])
    p.add_argument("id", help="e.g. P03, R02, S04")
    p.set_defaults(func=cmd_evidence_pack)

    p = add("check-schema", "validate one artifact file against its schema")
    p.add_argument("file")
    p.set_defaults(func=cmd_check_schema)

    p = add("theme-from-pptx", "extract a theme from a .pptx template")
    p.add_argument("pptx", help="path to the template .pptx")
    p.add_argument("--name", required=True, help="theme name to create under themes/")
    p.set_defaults(func=cmd_theme_from_pptx)

    p = add("review", "record a version-bound model review from a YAML file")
    p.add_argument("file", help="YAML with completed_checks, findings and manual_constraints")
    p.set_defaults(func=cmd_review)

    p = add("deliver", "record user acceptance of the built outputs")
    p.add_argument("--note", help="optional note (e.g. who accepted, conditions)")
    p.set_defaults(func=cmd_deliver)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (
        RunError,
        FileNotFoundError,
        FileExistsError,
        KeyError,
        RuntimeError,
        yaml.YAMLError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

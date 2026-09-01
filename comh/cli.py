"""comh — the communication harness CLI.

Commands mirror the artifact lifecycle:

    init-run <path>      scaffold a run workspace
    status               live state: artifacts (drift/staleness) + gates
    save <artifact>      record "produced from current upstream" (hash snapshot)
    confirm <gate>       user confirms brief / narrative (hard gate)
    validate [target]    schema + cross-artifact checks → qa/findings.yaml
    render <target>      deck → build/deck.pptx; report → build/report.docx
    evidence-pack ...    ID-chain slice for one page/beat/section (repair-loop QA)

Stage guards are enforced here, not by prompt discipline: downstream commands
refuse to run when an upstream gate is missing or invalidated.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from .artifacts import ARTIFACT_KEYS, load_artifact, validate_schema
from .evidence_pack import build_pack, format_pack
from .manifest import DERIVATION, GATE_OF_ARTIFACT, Manifest, RunError, find_run_root
from .render import render_deck, render_report
from .scaffold import init_run
from .validate import _BACKGROUND_FORBIDS_DARK, run_all, write_findings


def _resolve_run(args: argparse.Namespace) -> Path:
    root = find_run_root(Path(args.run).resolve() if args.run else Path.cwd())
    if root is None:
        raise RunError("not inside a run workspace (no run.yaml); use --run or cd into runs/<name>")
    return root


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
    manifest.mark_saved(key)
    print(f"saved '{key}' (upstream snapshot: {', '.join(DERIVATION[key])})")
    gate = GATE_OF_ARTIFACT.get(key)
    if gate and not manifest.gate_valid(gate):
        print(f"note: gate '{key}' needs user confirmation → `comh confirm {key}`")
    return 0


def cmd_confirm(args: argparse.Namespace) -> int:
    manifest = Manifest.load(_resolve_run(args))
    gate = args.gate
    # A gate may only be confirmed when its upstream gate (if any) is valid.
    if gate == "narrative":
        manifest.require_gate("brief")
    manifest.confirm_gate(gate)
    record = manifest.data["gates"][gate]
    print(f"gate '{gate}' confirmed at {record['at']}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    run_root = _resolve_run(args)
    if args.target != "all":
        print("note: per-artifact validation runs the same full check set; target is informational")
    findings = run_all(run_root)
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
    if args.target == "deck":
        manifest.require_gate("narrative")
        manifest.require_fresh("deck_plan")
        plan, findings = load_artifact(run_root, "deck_plan")
        if findings:
            raise RunError("deck_plan fails schema validation; run `comh validate all`")
        brief, _ = load_artifact(run_root, "brief")
        brief = brief or {}
        evidence, _ = load_artifact(run_root, "evidence")
        allow_dark = not any(
            _BACKGROUND_FORBIDS_DARK.search(c)
            for c in brief.get("constraints", {}).get("hard", [])
        )
        output = run_root / manifest.data["build"]["deck"]
        result = render_deck(
            plan, run_root, output,
            language=brief.get("language", "en"),
            evidence=evidence,
            allow_dark=allow_dark,
        )
        report_path = run_root / "qa" / "render-deck.yaml"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            yaml.safe_dump(
                {
                    "output": str(result.output),
                    "theme": result.theme,
                    "transition": result.transition,
                    "count": {
                        s: sum(1 for f in result.findings if f.severity == s)
                        for s in ("error", "warn", "info")
                    },
                    "findings": [f.as_dict() for f in result.findings],
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        for finding in result.findings:
            print(f"  [△] render: {finding.detail}")
        print(
            f"rendered deck → {output} (theme: {result.theme}, "
            f"transition: {result.transition or 'none'})"
        )
        if result.findings:
            print(f"render report → {report_path}")
        return 0
    if args.target == "report":
        manifest.require_fresh("report_plan")
        manifest.require_fresh("report_md")
        source = run_root / manifest.data["artifacts"]["report_md"]["path"]
        template = run_root / "templates" / "base.docx"
        output = run_root / manifest.data["build"]["report_docx"]
        render_report(source, template, output)
        canonical = manifest.data["artifacts"]["report_md"]["path"]
        print(f"rendered report → {output}; canonical deliverable: {canonical} (md-first)")
        return 0
    raise RunError("render target must be 'deck' or 'report'")


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
    p.add_argument("target", choices=["deck", "report"])
    p.set_defaults(func=cmd_render)

    p = add("evidence-pack", "ID-chain slice for a deck page / report section / beat")
    p.add_argument("artifact", choices=["deck", "report", "narrative"])
    p.add_argument("id", help="e.g. P03, R02, S04")
    p.set_defaults(func=cmd_evidence_pack)

    p = add("check-schema", "validate one artifact file against its schema")
    p.add_argument("file")
    p.set_defaults(func=cmd_check_schema)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RunError, FileNotFoundError, FileExistsError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

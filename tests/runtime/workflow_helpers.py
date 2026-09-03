"""Explicit simulated-user setup for lifecycle tests (never used by production)."""

from copy import deepcopy

import yaml

from comh.cli import main
from comh.decision_checks import BRIEF_FIELDS
from comh.dialogue import intake, latest
from comh.manifest import Manifest


def aligned(data):
    data = deepcopy(data)
    for key, default in {
        "delivery_context": "异步评审",
        "constraints": {"hard": [], "soft": []},
        "voice": {"style": "plain"},
        "visual_materials": "纯排版",
        "appearance": {"selection": "default", "review": "sample"},
        "presentation": {"setting": "general"},
    }.items():
        data.setdefault(key, default)
    data["alignment"] = {
        k: {
            "source": "user",
            "status": "provided",
            "basis": "test:simulated-user",
            "value": data[k],
        }
        for k in BRIEF_FIELDS
    }
    return data


def prepare(root):
    manifest = Manifest.load(root)
    if not manifest.data.get("interaction", {}).get("intake"):
        intake(
            manifest,
            {
                "goal": "Evaluate the fixture",
                "source_scope": "All fixture files",
                "basis": "test:simulated-user",
            },
        )
    coverage = {
        "sources": [
            {"file": p.relative_to(root).as_posix(), "status": "read", "locator": "entire fixture"}
            for p in sorted((root / "sources").rglob("*"))
            if p.is_file()
        ]
    }
    (root / "evidence/coverage.yaml").write_text(yaml.safe_dump(coverage, sort_keys=False))


def approve(root, target, node=None):
    args = ["present", target, "--run", str(root)]
    if node:
        args += ["--node", node]
    code = main(args)
    if code:
        return code
    request = latest(Manifest.load(root), target, node)
    return main(
        [
            "respond",
            request["id"],
            "--decision",
            "accepted",
            "--reply",
            "Fixture user accepts this version",
            "--source",
            "test:simulated-user",
            "--run",
            str(root),
        ]
    )


def simulated_reader(root):
    path = root / "qa/reader-output.md"
    path.write_text("Synthetic reader result for lifecycle tests; not a real agent evaluation.\n")
    return {
        "output": "qa/reader-output.md",
        "executor": "test:simulated-reader",
        "input_scope": "test:fixture output only",
    }

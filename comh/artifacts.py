"""Artifact loading and JSON Schema validation.

Schemas keep the required core small; unknown fields are allowed everywhere
(``additionalProperties: true``) so the model can extend artifacts freely.
Validators warn on unknown open-vocabulary values instead of rejecting them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).parent / "schemas"

ARTIFACT_KEYS = ("evidence", "brief", "narrative", "deck_plan", "report_plan")

KNOWN_CLAIM_STATUSES = {"supported", "partial", "background", "assumption", "needs_research"}
KNOWN_PAGE_ROLES = {"cover", "agenda", "section_divider", "content", "closing", "appendix"}


@dataclass
class Finding:
    artifact: str
    check: str
    severity: str  # error | warn | info
    verdict: str  # pass | fail
    detail: str
    owning_artifact: str = field(default="")

    def as_dict(self) -> dict[str, str]:
        return {
            "artifact": self.artifact,
            "check": self.check,
            "severity": self.severity,
            "verdict": self.verdict,
            "detail": self.detail,
            "owning_artifact": self.owning_artifact or self.artifact,
        }


@cache
def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate_schema(name: str, data: Any) -> list[str]:
    errors = sorted(_validator(name).iter_errors(data), key=lambda e: list(e.absolute_path))
    return [
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    ]


def load_artifact(run_root: Path, key: str) -> tuple[Any, list[Finding]]:
    """Load an artifact file and schema-validate it. Missing files yield one error."""
    from .manifest import Manifest  # local import to avoid cycle in scaffold usage

    manifest = Manifest.load(run_root)
    path = run_root / manifest.data["artifacts"][key]["path"]
    if not path.is_file():
        return None, [
            Finding(key, "schema", "error", "fail", f"file missing: {path}", key)
        ]
    try:
        data = load_yaml(path)
    except yaml.YAMLError as error:
        location = getattr(getattr(error, "problem_mark", None), "line", None)
        where = f" (line {location + 1})" if location is not None else ""
        return None, [
            Finding(key, "schema", "error", "fail",
                    f"{path.name} is not valid YAML{where}: fix the syntax and retry", key)
        ]
    findings = [
        Finding(key, "schema", "error", "fail", message, key)
        for message in validate_schema(key, data)
    ]
    return data, findings

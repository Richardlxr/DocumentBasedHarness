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
KNOWN_PAGE_ROLES = {
    "cover",
    "agenda",
    "section_divider",
    "content",
    "closing",
    "appendix",
    "hero_split",
    "fullscreen_backdrop",
    "timeline",
    "versus",
}


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
    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node)
            if key in result:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key: {key}", key_node.start_mark
                )
            result[key] = loader.construct_object(value_node)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)


def validate_schema(name: str, data: Any) -> list[str]:
    errors = sorted(
        _validator(name).iter_errors(data), key=lambda e: tuple(map(str, e.absolute_path))
    )
    messages = [
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    ]
    if not errors:
        fields = {
            "evidence": ("sources", "items"),
            "narrative": ("claims", "story"),
            "report_plan": ("sections",),
        }.get(name, ())
        groups = [(field, data.get(field, [])) for field in fields]
        if name == "deck_plan":
            groups = [("pages", data["deck"]["pages"])]
        for label, entries in groups:
            seen = set()
            for entry in entries:
                if entry["id"] in seen:
                    messages.append(f"{label}: duplicate ID '{entry['id']}'")
                seen.add(entry["id"])
    return messages


def load_artifact(run_root: Path, key: str) -> tuple[Any, list[Finding]]:
    """Load an artifact file and schema-validate it. Missing files yield one error."""
    from .manifest import Manifest  # local import to avoid cycle in scaffold usage

    manifest = Manifest.load(run_root)
    path = run_root / manifest.data["artifacts"][key]["path"]
    if not path.is_file():
        return None, [Finding(key, "schema", "error", "fail", f"file missing: {path}", key)]
    try:
        data = load_yaml(path)
    except yaml.YAMLError as error:
        location = getattr(getattr(error, "problem_mark", None), "line", None)
        where = f" (line {location + 1})" if location is not None else ""
        return None, [
            Finding(
                key,
                "schema",
                "error",
                "fail",
                f"{path.name} is not valid YAML{where}: fix the syntax and retry",
                key,
            )
        ]
    findings = [
        Finding(key, "schema", "error", "fail", message, key)
        for message in validate_schema(key, data)
    ]
    return (None if findings else data), findings

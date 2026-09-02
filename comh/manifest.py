"""Run workspace manifest: artifact registry, gates, and live state computation.

The manifest (``run.yaml``) is a cache of two facts that cannot be recomputed
from files alone:

1. when an artifact was *saved* (produced from the current upstream state), and
2. when a gate was *confirmed* by the user.

Everything else — drift, staleness, gate validity — is computed live by
comparing current file hashes against the recorded ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from .lineage import hash_dir, hash_file

MANIFEST_NAME = "run.yaml"

# Static derivation graph. Upstream of "sources" is the sources/ directory.
DERIVATION: dict[str, list[str]] = {
    "evidence": ["sources"],
    "brief": ["evidence"],
    "narrative": ["brief", "evidence"],
    "deck_plan": ["narrative", "brief"],
    "report_plan": ["narrative", "brief"],
    "report_md": ["report_plan", "narrative"],
}

GATE_OF_ARTIFACT = {"brief": "brief", "narrative": "narrative"}

BUILD_OUTPUTS = {"deck": "build/deck.pptx", "report_docx": "build/report.docx"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def default_manifest(name: str) -> dict:
    return {
        "version": 1,
        "name": name,
        "created": now_iso(),
        "artifacts": {
            key: {
                "path": path,
                "hash": None,
                "saved_at": None,
                "upstream": {up: None for up in ups},
            }
            for key, (path, ups) in {
                "evidence": ("evidence/evidence.yaml", DERIVATION["evidence"]),
                "brief": ("brief/brief.yaml", DERIVATION["brief"]),
                "narrative": ("narrative/narrative.yaml", DERIVATION["narrative"]),
                "deck_plan": ("projection/deck_plan.yaml", DERIVATION["deck_plan"]),
                "report_plan": ("projection/report_plan.yaml", DERIVATION["report_plan"]),
                "report_md": ("documents/report.md", DERIVATION["report_md"]),
            }.items()
        },
        "gates": {
            "brief": {"confirmed": False, "at": None, "hash": None},
            "narrative": {"confirmed": False, "at": None, "hash": None},
        },
        "build": dict(BUILD_OUTPUTS),
        "deliveries": [],
    }


def find_run_root(start: Path) -> Path | None:
    for candidate in [start, *start.resolve().parents]:
        if (candidate / MANIFEST_NAME).is_file():
            return candidate
    return None


class RunError(RuntimeError):
    """Raised for manifest/guard violations. Message is user-facing."""


@dataclass
class ArtifactState:
    key: str
    exists: bool
    state: str  # absent | unsaved | modified | stale | confirmed | saved
    detail: str

    @property
    def is_fresh(self) -> bool:
        return self.state in ("confirmed", "saved")


class Manifest:
    def __init__(self, root: Path, data: dict) -> None:
        self.root = root
        self.data = data
        self.path = root / MANIFEST_NAME

    # -- persistence ---------------------------------------------------------

    @classmethod
    def load(cls, root: Path) -> Manifest:
        path = root / MANIFEST_NAME
        if not path.is_file():
            raise RunError(f"no {MANIFEST_NAME} under {root}; run `comh init-run` first")
        return cls(root, yaml.safe_load(path.read_text(encoding="utf-8")))

    def save(self) -> None:
        self.path.write_text(
            yaml.safe_dump(self.data, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    # -- hashing helpers -----------------------------------------------------

    def artifact_path(self, key: str) -> Path:
        return self.root / self.data["artifacts"][key]["path"]

    def _current_hash(self, upstream: str) -> str | None:
        if upstream == "sources":
            return hash_dir(self.root / "sources")
        record = self.data["artifacts"].get(upstream)
        if record is None or not (self.root / record["path"]).is_file():
            return None
        return hash_file(self.root / record["path"])

    # -- state computation ---------------------------------------------------

    def artifact_state(self, key: str) -> ArtifactState:
        record = self.data["artifacts"][key]
        file = self.root / record["path"]
        if not file.is_file():
            return ArtifactState(key, False, "absent", "file missing")
        current = hash_file(file)
        if record["hash"] is None:
            return ArtifactState(key, True, "unsaved", "never saved via `comh save`")
        if current != record["hash"]:
            return ArtifactState(key, True, "modified", "changed since last save")
        for up, recorded in record["upstream"].items():
            if recorded is not None and self._current_hash(up) != recorded:
                return ArtifactState(key, True, "stale", f"upstream changed: {up}")
        # Transitive drift: an upstream artifact that is itself stale/modified
        # means this artifact was derived from state that no longer holds.
        for up in DERIVATION[key]:
            if up == "sources":
                continue
            upstream_state = self.artifact_state(up)
            if upstream_state.state in ("stale", "modified", "unsaved"):
                return ArtifactState(
                    key, True, "stale", f"upstream '{up}' is {upstream_state.state}"
                )
        if GATE_OF_ARTIFACT.get(key) and self.gate_valid(GATE_OF_ARTIFACT[key]):
            return ArtifactState(key, True, "confirmed", "gate confirmed")
        return ArtifactState(key, True, "saved", "up to date with upstream")

    def gate_valid(self, gate: str) -> bool:
        record = self.data["gates"][gate]
        if not record.get("confirmed"):
            return False
        artifact = self.data["artifacts"][gate]
        file = self.root / artifact["path"]
        return file.is_file() and hash_file(file) == record["hash"]

    # -- mutations -----------------------------------------------------------

    def mark_saved(self, key: str) -> None:
        record = self.data["artifacts"][key]
        file = self.root / record["path"]
        if not file.is_file():
            raise RunError(f"cannot save '{key}': {record['path']} does not exist")
        record["hash"] = hash_file(file)
        record["saved_at"] = now_iso()
        record["upstream"] = {
            up: self._current_hash(up) for up in DERIVATION[key]
        }
        # Re-saving identical content must not invalidate a user gate: the gate
        # pins what the user confirmed, and the bytes did not change. Changed
        # content always invalidates.
        gate = GATE_OF_ARTIFACT.get(key)
        if gate:
            gate_record = self.data["gates"][gate]
            if gate_record.get("confirmed") and gate_record.get("hash") != record["hash"]:
                self.data["gates"][gate] = {"confirmed": False, "at": None, "hash": None}
        self.save()

    def confirm_gate(self, gate: str) -> None:
        if gate not in self.data["gates"]:
            raise RunError(f"unknown gate '{gate}' (known: brief, narrative)")
        artifact = self.data["artifacts"][gate]
        file = self.root / artifact["path"]
        if not file.is_file():
            raise RunError(f"cannot confirm gate '{gate}': {artifact['path']} does not exist")
        self.data["gates"][gate] = {
            "confirmed": True,
            "at": now_iso(),
            "hash": hash_file(file),
        }
        self.save()

    # -- delivery acceptance ---------------------------------------------------

    def delivery_state(self) -> tuple[str, dict | None]:
        """(state, record) for the latest delivery: none | accepted | invalidated."""
        records = self.data.get("deliveries") or []
        if not records:
            return "none", None
        record = records[-1]
        for rel, recorded in (record.get("outputs") or {}).items():
            path = self.root / rel
            if not path.is_file() or hash_file(path) != recorded:
                return "invalidated", record
        return "accepted", record

    def record_delivery(self, note: str | None = None) -> dict:
        """Pin the current build outputs as user-accepted (the final gate)."""
        outputs = {}
        for rel in self.data.get("build", {}).values():
            path = self.root / str(rel)
            if path.is_file():
                outputs[str(rel)] = hash_file(path)
        record = {"accepted_at": now_iso(), "outputs": outputs}
        if note:
            record["note"] = note
        self.data.setdefault("deliveries", []).append(record)
        self.save()
        return record

    # -- guards ----------------------------------------------------------------

    def require_saved(self, key: str) -> None:
        state = self.artifact_state(key)
        if state.state == "absent":
            raise RunError(f"'{key}' is missing ({self.data['artifacts'][key]['path']})")
        if state.state == "unsaved":
            raise RunError(f"'{key}' was never saved; run `comh save {key}` first")

    def require_gate(self, gate: str) -> None:
        if not self.data["gates"][gate]["confirmed"]:
            raise RunError(f"gate '{gate}' is not confirmed; `comh confirm {gate}` with the user")
        if not self.gate_valid(gate):
            raise RunError(
                f"gate '{gate}' was invalidated by later edits; re-confirm with the user"
            )

    def require_fresh(self, key: str) -> None:
        self.require_saved(key)
        state = self.artifact_state(key)
        if state.state in ("modified", "stale"):
            raise RunError(
                f"'{key}' is {state.state} ({state.detail}); "
                f"re-derive it from upstream or restore upstream, then `comh save {key}`"
            )

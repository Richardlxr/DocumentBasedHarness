"""Run workspace manifest: artifact registry, gates, and live state computation.

The manifest (``run.yaml``) is a cache of two facts that cannot be recomputed
from files alone:

1. when an artifact was *saved* (produced from the current upstream state), and
2. when a gate was *confirmed* by the user.

Everything else — drift, staleness, gate validity — is computed live by
comparing current file hashes against the recorded ones.
"""

from __future__ import annotations

import os
import platform
import sys
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

from .contracts import OUTPUT_ARTIFACT, requested_outputs, required_artifacts
from .lineage import hash_bytes, hash_dir, hash_file

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

BUILD_OUTPUTS = {
    "deck": "build/deck.pptx",
    "deck_html": "build/deck.html",
    "report_docx": "build/report.docx",
}


def upstream_chain(key: str) -> set[str]:
    keys, stack = {key}, [key]
    while stack:
        for up in DERIVATION.get(stack.pop(), []):
            if up != "sources" and up not in keys:
                keys.add(up)
                stack.append(up)
    return keys


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
        "build_records": {},
        "deliveries": [],
        "interaction": {"version": 1, "mode": "checkpoints", "requests": []},
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
        self._cache: dict | None = None

    # -- read-only snapshot scope ---------------------------------------------

    @contextmanager
    def reading(self):
        """Hash each file at most once for the duration of one read-only command.

        Staleness is still derived from the files on disk, never from the
        manifest — this only stops a single ``comh status`` from re-reading
        ``sources/`` fifteen times, which dominates the command once a run
        holds real material. Outside this scope nothing is cached, so guards
        (`require_fresh`, `mark_saved`, `require_build`) always read live.

        A mutation inside the scope drops the cache, so no check can act on a
        hash taken before its own write.
        """
        outer, self._cache = self._cache, {} if self._cache is None else self._cache
        try:
            yield self
        finally:
            self._cache = outer

    def _cached(self, key: tuple, compute):
        if self._cache is None:
            return compute()
        if key not in self._cache:
            self._cache[key] = compute()
        return self._cache[key]

    # -- persistence ---------------------------------------------------------

    @classmethod
    def load(cls, root: Path) -> Manifest:
        path = root / MANIFEST_NAME
        if not path.is_file():
            raise RunError(f"no {MANIFEST_NAME} under {root}; run `comh init-run` first")
        return cls(root, yaml.safe_load(path.read_text(encoding="utf-8")))

    def save(self) -> None:
        self._cache = None if self._cache is None else {}
        # A failed write must not truncate the only lifecycle record. One writer
        # owns a run; this atomic replace is not a multi-writer locking protocol.
        temporary = None
        try:
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.root, delete=False
            ) as file:
                temporary = Path(file.name)
                file.write(yaml.safe_dump(self.data, allow_unicode=True, sort_keys=False))
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    # -- hashing helpers -----------------------------------------------------

    def artifact_path(self, key: str) -> Path:
        return self.root / self.data["artifacts"][key]["path"]

    def _hash_file(self, path: Path) -> str:
        return self._cached(("file", str(path)), lambda: hash_file(path))

    def _current_hash(self, upstream: str) -> str | None:
        if upstream == "sources":
            return self._cached(("dir", "sources"), lambda: hash_dir(self.root / "sources"))
        record = self.data["artifacts"].get(upstream)
        if record is None or not (self.root / record["path"]).is_file():
            return None
        return self._hash_file(self.root / record["path"])

    # -- state computation ---------------------------------------------------

    def artifact_state(self, key: str) -> ArtifactState:
        return self._cached(("state", key), lambda: self._artifact_state(key))

    def _artifact_state(self, key: str) -> ArtifactState:
        record = self.data["artifacts"][key]
        file = self.root / record["path"]
        if not file.is_file():
            return ArtifactState(key, False, "absent", "file missing")
        current = self._hash_file(file)
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
            if not upstream_state.is_fresh:
                return ArtifactState(
                    key, True, "stale", f"upstream '{up}' is {upstream_state.state}"
                )
        if (
            GATE_OF_ARTIFACT.get(key)
            and self._gate_content_valid(key)
            and (key != "narrative" or self.gate_valid("brief"))
        ):
            return ArtifactState(key, True, "confirmed", "gate confirmed")
        return ArtifactState(key, True, "saved", "up to date with upstream")

    def gate_valid(self, gate: str) -> bool:
        return (
            self._gate_content_valid(gate)
            and self.artifact_state(gate).is_fresh
            and (gate != "narrative" or self.gate_valid("brief"))
        )

    def _gate_content_valid(self, gate: str) -> bool:
        from .dialogue import latest, valid

        record = self.data["gates"][gate]
        if not record.get("confirmed"):
            return False
        artifact = self.data["artifacts"][gate]
        file = self.root / artifact["path"]
        request = latest(self, gate)
        return (
            file.is_file()
            and self._hash_file(file) == record["hash"]
            and bool(request)
            and record.get("request_id") == request["id"]
            and request["state"] == "accepted"
            and valid(self, gate)
        )

    # -- mutations -----------------------------------------------------------

    def mark_saved(self, key: str) -> None:
        record = self.data["artifacts"][key]
        file = self.root / record["path"]
        if not file.is_file():
            raise RunError(f"cannot save '{key}': {record['path']} does not exist")
        record["hash"] = hash_file(file)
        record["saved_at"] = now_iso()
        record["upstream"] = {up: self._current_hash(up) for up in DERIVATION[key]}
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
        raise RunError(
            "direct confirmation is unsupported; present a version and record its user response"
        )

    # -- delivery acceptance ---------------------------------------------------

    def brief(self) -> dict:
        path = self.artifact_path("brief")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if not isinstance(data, dict):
            raise RunError("brief must be a YAML object")
        return data

    def input_snapshot(self, keys: set[str]) -> dict:
        """Content dependencies, including non-artifact render inputs."""
        snapshot = {key: self._current_hash(key) for key in sorted(keys)}
        for directory in ("sources", "assets", "themes", "templates"):
            snapshot[f"directory:{directory}"] = hash_dir(self.root / directory)
        repo = Path(__file__).resolve().parents[1]
        snapshot["shared-themes"] = hash_dir(repo / "themes")
        # Exclude caches; pin the implementation and bundled renderer resources.
        files = sorted(
            p
            for folder in (repo / "comh", repo / "docx_harness")
            for p in folder.rglob("*")
            if p.is_file() and p.suffix in {".py", ".json", ".js", ".css", ".docx"}
        )
        snapshot["engine"] = hash_bytes(
            "\n".join(f"{p.relative_to(repo)}:{hash_file(p)}" for p in files).encode()
        )
        if getattr(sys, "frozen", False):
            # PyInstaller stores implementation bytecode inside its executable.
            snapshot["frozen-engine"] = hash_file(Path(sys.executable))
        snapshot["runtime"] = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": {
                name: version(name)
                for name in (
                    "python-pptx",
                    "python-docx",
                    "myst-parser",
                    "markdown-it-py",
                    "Pillow",
                )
            },
            "tools": {
                name: os.environ.get(name)
                for name in ("DRAWIO_CLI", "DRAWIO_ACCEPT_VERSION", "COMH_CHROME")
            },
        }
        return snapshot

    def output_selection(self) -> set[str]:
        brief = self.brief()
        outputs = requested_outputs(brief)
        keys = required_artifacts(brief)
        # Include compiled companions that actually exist for selected media.
        for key, artifact in OUTPUT_ARTIFACT.items():
            rel = self.data.get("build", {}).get(key)
            if artifact in keys and rel and (self.root / rel).is_file():
                outputs.add(key)
        return outputs

    def output_path(self, key: str) -> Path:
        if key == "report_md":
            return self.artifact_path(key)
        return self.root / self.data.get("build", {}).get(key, BUILD_OUTPUTS[key])

    def review_snapshot(self) -> dict:
        from .dialogue import accepted_receipts

        snapshot = self.input_snapshot(required_artifacts(self.brief()))
        outputs = self.output_selection()
        snapshot["outputs"] = {
            key: hash_file(self.output_path(key)) if self.output_path(key).is_file() else None
            for key in sorted(outputs)
        }
        snapshot["build_records"] = {
            key: self.data.get("build_records", {}).get(key)
            for key in sorted(outputs - {"report_md"})
        }
        snapshot["render_qa"] = {}
        for key, record in snapshot["build_records"].items():
            qa = self.root / record["qa_path"] if record else None
            snapshot["render_qa"][key] = hash_file(qa) if qa and qa.is_file() else None
        snapshot["gates"] = self.data["gates"]
        snapshot["decisions"] = accepted_receipts(self)
        return deepcopy(snapshot)

    def begin_build(self, key: str) -> dict:
        self.data.setdefault("build", {}).setdefault(key, BUILD_OUTPUTS[key])
        self.data.setdefault("build_records", {}).pop(key, None)
        # Even a byte-identical re-render requires a new read-through.
        self.data["build_generation"] = self.data.get("build_generation", 0) + 1
        self.save()
        return self.input_snapshot(upstream_chain(OUTPUT_ARTIFACT[key]))

    def record_build(self, key: str, inputs: dict, qa_path: Path, success: bool) -> None:
        self.data.setdefault("build_records", {})[key] = {
            "generation": self.data["build_generation"],
            "inputs": inputs,
            "output": hash_file(self.output_path(key)) if self.output_path(key).is_file() else None,
            "qa_path": qa_path.relative_to(self.root).as_posix(),
            "qa_hash": hash_file(qa_path),
            "success": success,
        }
        self.save()

    def require_build(self, key: str) -> None:
        record = self.data.get("build_records", {}).get(key)
        path = self.output_path(key)
        if not record or not record.get("success") or not path.is_file():
            raise RunError(f"'{key}' has no successful build receipt; re-render it")
        qa = self.root / record["qa_path"]
        if (
            record["inputs"] != self.input_snapshot(upstream_chain(OUTPUT_ARTIFACT[key]))
            or record["output"] != hash_file(path)
            or not qa.is_file()
            or record["qa_hash"] != hash_file(qa)
        ):
            raise RunError(f"'{key}' build is stale or its output/QA changed; re-render it")

    def delivery_state(self) -> tuple[str, dict | None]:
        """(state, record) for the latest delivery: none | accepted | invalidated."""
        from .dialogue import latest, valid

        records = self.data.get("deliveries") or []
        if not records:
            return "none", None
        record = records[-1]
        if not record.get("inputs"):
            return "invalidated", record  # legacy acceptance did not pin inputs
        decision = latest(self, "delivery")
        if (
            not decision
            or record.get("request_id") != decision["id"]
            or not valid(self, "delivery")
        ):
            return "invalidated", record
        try:
            if record["inputs"] != self.review_snapshot():
                return "invalidated", record
        except (RunError, KeyError, yaml.YAMLError):
            return "invalidated", record
        review = self.root / "qa" / "model-findings.yaml"
        if not review.is_file() or record.get("review_hash") != hash_file(review):
            return "invalidated", record
        for rel, recorded in (record.get("outputs") or {}).items():
            path = self.root / rel
            if not path.is_file() or hash_file(path) != recorded:
                return "invalidated", record
        return "accepted", record

    def record_delivery(self, note: str | None = None) -> dict:
        """Pin the current build outputs as user-accepted (the final gate)."""
        from .dialogue import latest, valid

        if not valid(self, "delivery"):
            raise RunError("delivery needs an accepted current presentation")
        status, existing = self.delivery_state()
        if status == "accepted" and existing.get("note") == note:
            return existing
        outputs = {}
        for key in self.output_selection():
            path = self.output_path(key)
            outputs[path.relative_to(self.root).as_posix()] = hash_file(path)
        record = {
            "accepted_at": now_iso(),
            "request_id": latest(self, "delivery")["id"],
            "outputs": outputs,
            "inputs": self.review_snapshot(),
            "review_hash": hash_file(self.root / "qa" / "model-findings.yaml"),
        }
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
            raise RunError(f"gate '{gate}' is not confirmed; `comh present {gate}` to the user")
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

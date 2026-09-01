from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ..errors import DocumentError

PROJECT_CONFIG_VERSION = 1
PROJECT_NAME = re.compile(r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")

_REQUIRED_FIELDS = {
    "name",
    "template",
    "extensions",
    "documents",
    "build",
    "source",
    "output",
}
_OPTIONAL_FIELDS = {"template_preset", "style_manifest"}
_KNOWN_FIELDS = {"version", *_REQUIRED_FIELDS, *_OPTIONAL_FIELDS}


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    root: Path
    name: str
    template: Path
    extensions: Path
    documents: Path
    build: Path
    source: Path
    output: Path
    template_preset: str | None = None
    style_manifest: Path | None = None


def _inside(root: Path, value: str, *, field: str) -> Path:
    candidate = (root / value).resolve()
    if not candidate.is_relative_to(root):
        raise DocumentError(f"project path escapes its root: {field} = {value!r}")
    return candidate


def _required_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DocumentError(f"project configuration field must be a non-empty string: {key}")
    return value


def _optional_string(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DocumentError(f"project configuration field must be a non-empty string: {key}")
    return value


def load_project(project: str | Path) -> ProjectConfig:
    """Load and validate one managed Project's versioned configuration.

    Git ownership is validated separately. Rendering intentionally depends on versioned Project
    inputs, not on the physical representation of the surrounding Git checkout.
    """

    root = Path(project).resolve()
    if not root.is_dir():
        raise DocumentError(f"managed project directory does not exist: {root}")

    config_path = root / "project.toml"
    if not config_path.is_file():
        raise DocumentError(f"project configuration does not exist: {config_path}")
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise DocumentError(f"cannot read project configuration: {error}") from error

    if data.get("version") != PROJECT_CONFIG_VERSION:
        raise DocumentError(f"unsupported project configuration version: {data.get('version')}")
    unknown = sorted(set(data) - _KNOWN_FIELDS)
    if unknown:
        raise DocumentError(f"unknown project configuration field: {unknown[0]}")

    name = _required_string(data, "name")
    if not PROJECT_NAME.fullmatch(name):
        raise DocumentError(f"invalid managed project name: {name}")

    style_manifest_value = _optional_string(data, "style_manifest")
    config = ProjectConfig(
        root=root,
        name=name,
        template=_inside(root, _required_string(data, "template"), field="template"),
        extensions=_inside(root, _required_string(data, "extensions"), field="extensions"),
        documents=_inside(root, _required_string(data, "documents"), field="documents"),
        build=_inside(root, _required_string(data, "build"), field="build"),
        source=_inside(root, _required_string(data, "source"), field="source"),
        output=_inside(root, _required_string(data, "output"), field="output"),
        template_preset=_optional_string(data, "template_preset"),
        style_manifest=(
            _inside(root, style_manifest_value, field="style_manifest")
            if style_manifest_value is not None
            else None
        ),
    )

    required_inputs = [config.template, config.extensions, config.documents, config.source]
    if config.style_manifest is not None:
        required_inputs.append(config.style_manifest)
    missing = next((path for path in required_inputs if not path.exists()), None)
    if missing is not None:
        raise DocumentError(f"managed project input does not exist: {missing}")
    if not config.template.is_file():
        raise DocumentError(f"project template path is not a file: {config.template}")
    if not config.extensions.is_file():
        raise DocumentError(f"project extensions path is not a file: {config.extensions}")
    if not config.documents.is_dir():
        raise DocumentError(f"project documents path is not a directory: {config.documents}")
    if not config.source.is_file():
        raise DocumentError(f"project source path is not a file: {config.source}")
    if not config.source.is_relative_to(config.documents):
        raise DocumentError(f"managed project source must be inside {config.documents}")
    if not config.output.is_relative_to(config.build):
        raise DocumentError(f"managed project output must be inside {config.build}")
    if config.style_manifest is not None and not config.style_manifest.is_file():
        raise DocumentError(f"project style_manifest path is not a file: {config.style_manifest}")
    return config

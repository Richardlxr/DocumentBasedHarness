"""Versioned appearance contracts. Deliberately no slots, density or narrative structure."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from ..artifacts import load_yaml
from .inspect import inspect_pptx, theme_tokens
from .package import NS, Package, StyleError, descendants, shape_id, shapes

_SCOPES = ("master", "layout", "slide")
_COLORS = (
    "background",
    "title",
    "text",
    "muted",
    "accent",
    "accent_soft",
    "card_fill",
    "card_line",
)
_SIZES = (
    "cover_title",
    "banner_title",
    "content_title",
    "body",
    "body_wide",
    "detail",
    "caption",
    "card_value",
    "card_label",
    "callout",
    "kicker",
    "footer",
    "index_number",
)


def _object(properties, required=()):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(required),
    }


TOKENS = _object(
    {
        "colors": _object({k: {"type": "string", "pattern": "^[0-9A-Fa-f]{6}$"} for k in _COLORS}),
        "fonts": _object(
            {
                k: {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"type": "string", "minLength": 1},
                }
                for k in ("latin", "cjk")
            }
        ),
        "sizes": _object({k: {"type": "integer", "minimum": 9, "maximum": 96} for k in _SIZES}),
        "font_styles": _object(
            {
                role: _object({"bold": {"type": "boolean"}, "italic": {"type": "boolean"}})
                for role in ("title", "body")
            }
        ),
    }
)
SURFACE = _object(
    {
        "slide": {"type": "integer", "minimum": 1},
        "keep": _object(
            {
                k: {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "integer", "minimum": 1},
                }
                for k in _SCOPES
            },
            _SCOPES,
        ),
        "tokens": TOKENS,
        "single_line": _object(
            {
                k: {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "integer", "minimum": 1},
                }
                for k in _SCOPES
            }
        ),
        "protect": _object(
            {
                k: {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "integer", "minimum": 1},
                }
                for k in _SCOPES
            }
        ),
    },
    ("slide", "keep"),
)
SCHEMA = _object(
    {
        "version": {"const": 1},
        "kind": {"const": "pptx-style"},
        "name": {"type": "string", "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]*$"},
        "source": {"type": "string", "minLength": 1},
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "tokens": TOKENS,
        "surfaces": {
            "type": "object",
            "minProperties": 1,
            "propertyNames": {"enum": ["cover", "content", "section_divider", "closing"]},
            "additionalProperties": SURFACE,
        },
    },
    ("version", "kind", "name", "source", "sha256", "tokens", "surfaces"),
)


@dataclass(frozen=True, slots=True)
class Surface:
    role: str
    slide: int
    keep: tuple[tuple[str, tuple[int, ...]], ...]
    token_json: str
    protect: tuple[tuple[str, tuple[int, ...]], ...] = ()
    single_line: tuple[tuple[str, tuple[int, ...]], ...] = ()

    def selected(self, scope: str) -> tuple[int, ...]:
        return dict(self.keep)[scope]

    @property
    def tokens(self) -> dict:
        return json.loads(self.token_json)


@dataclass(frozen=True, slots=True)
class StyleTemplate:
    name: str
    path: Path
    source: Path
    source_hash: str
    profile_hash: str
    token_json: str
    surfaces: tuple[Surface, ...]

    @property
    def tokens(self) -> dict:
        return json.loads(self.token_json)

    def surface(self, role: str) -> Surface:
        found = next((s for s in self.surfaces if s.role == role), None)
        if found:
            return found
        content = next((s for s in self.surfaces if s.role == "content"), None)
        if content and role not in {"cover", "section_divider", "closing"}:
            return content
        raise StyleError(f"style '{self.name}' has no {role} appearance surface")


def load_style(run_root: Path, ref: str) -> StyleTemplate:
    if not isinstance(ref, str) or Path(ref).is_absolute():
        raise StyleError("pptx_style must be a relative path under templates/")
    allowed = run_root.resolve() / "templates"
    path = (run_root / ref).resolve()
    if not path.is_relative_to(allowed) or not path.is_file():
        raise StyleError(f"style profile must exist under templates/: {ref}")
    try:
        data = load_yaml(path)
    except (yaml.YAMLError, OSError) as error:
        raise StyleError(f"cannot load style profile {ref}: {error}") from error
    errors = list(Draft202012Validator(SCHEMA).iter_errors(data))
    if errors:
        e = errors[0]
        raise StyleError(
            f"{ref}:{'.'.join(map(str, e.path))}: {e.message}; "
            "style profiles cannot specify content structure, density or slots"
        )
    source = (path.parent / data["source"]).resolve()
    if Path(data["source"]).is_absolute() or not source.is_relative_to(path.parent):
        raise StyleError("style source must remain inside its template directory")
    if not source.is_file():
        raise StyleError(f"style source missing: {source}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != data["sha256"]:
        raise StyleError("style source hash changed; inspect and rebind the style profile")
    surfaces = tuple(
        Surface(
            role,
            s["slide"],
            tuple((scope, tuple(s["keep"][scope])) for scope in _SCOPES),
            json.dumps(s.get("tokens", {})),
            tuple((scope, tuple(ids)) for scope, ids in s.get("protect", {}).items()),
            tuple((scope, tuple(ids)) for scope, ids in s.get("single_line", {}).items()),
        )
        for role, s in data["surfaces"].items()
    )
    package = Package(source)
    for surface in surfaces:
        for scope, ids in surface.protect:
            if not set(ids) <= set(surface.selected(scope)):
                raise StyleError(f"{surface.role}/{scope}: protected shapes must also be kept")
        for scope, ids in surface.single_line:
            if not set(ids) <= set(surface.selected(scope)):
                raise StyleError(f"{surface.role}/{scope}: single_line shapes must also be kept")
        for scope, part in package.scopes(surface.slide).items():
            roots = shapes(package.tree(part))
            available = {shape_id(s): s for s in descendants(roots)}
            protected = dict(surface.protect).get(scope, ())
            if not set(protected) <= {shape_id(s) for s in roots}:
                raise StyleError(
                    f"{surface.role}/{scope}: protect the containing group for nested icons"
                )
            if not set(dict(surface.single_line).get(scope, ())) <= {shape_id(s) for s in roots}:
                raise StyleError(f"{surface.role}/{scope}: single_line needs a top-level text box")
            for identity in surface.selected(scope):
                node = available.get(identity)
                if node is None:
                    raise StyleError(f"{surface.role}/{scope}: shape {identity} does not exist")
                if node.find(".//p:ph", NS) is not None:
                    raise StyleError(
                        f"{surface.role}/{scope}/{identity}: content placeholders "
                        "cannot be appearance assets"
                    )
                if node.findall(".//a:graphic", NS) or node.findall(".//a:hlinkClick", NS):
                    raise StyleError(
                        f"{surface.role}/{scope}/{identity}: charts, OLE and actions "
                        "cannot be imported as appearance assets"
                    )
    return StyleTemplate(
        data["name"],
        path,
        source,
        digest,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        json.dumps(data["tokens"]),
        surfaces,
    )


def import_style(source: Path, name: str, run_root: Path) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", name):
        raise StyleError("style name must contain only letters, digits, '-' or '_'")
    inventory = inspect_pptx(source)
    root = run_root.resolve() / "templates" / name
    if root.resolve() != root:
        raise StyleError("style destination must not traverse symlinks")
    profile = root / "style.yaml"
    if root.exists():
        raise StyleError(f"style already exists; inspect/edit its profile explicitly: {root}")
    root.mkdir(parents=True)
    try:
        shutil.copyfile(source, root / "source.pptx")
        (root / "inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        data = {
            "version": 1,
            "kind": "pptx-style",
            "name": name,
            "source": "source.pptx",
            "sha256": inventory["sha256"],
            "tokens": theme_tokens(Package(source)),
            "surfaces": {},
        }
        profile.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    except Exception:
        # Preserve partial imports for diagnosis; never remove user template data.
        raise
    return profile

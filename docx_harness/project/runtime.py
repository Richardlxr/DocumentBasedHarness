from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from ..diagrams.model import DiagramConverterRegistry, default_diagram_registry
from ..errors import DocumentError
from ..extension import ExtensionRegistry
from ..lifecycle import RenderHooks
from ..table_format import TableFormatProfile
from .config import ProjectConfig, load_project
from .loader import load_project_module


@dataclass(frozen=True, slots=True)
class ProjectRuntime:
    config: ProjectConfig
    module: ModuleType
    registry: ExtensionRegistry
    diagram_registry: DiagramConverterRegistry
    table_profile: TableFormatProfile | None
    hooks: RenderHooks


def _extension_registry_from_module(module: ModuleType) -> ExtensionRegistry:
    factory = getattr(module, "create_registry", None)
    if not callable(factory):
        raise DocumentError("project extensions.py must define create_registry()")
    registry = factory()
    if not isinstance(registry, ExtensionRegistry):
        raise DocumentError("project create_registry() must return ExtensionRegistry")
    return registry


def _diagram_registry_from_module(module: ModuleType) -> DiagramConverterRegistry:
    factory = getattr(module, "create_diagram_registry", None)
    if factory is None:
        return default_diagram_registry()
    if not callable(factory):
        raise DocumentError("project create_diagram_registry must be callable")
    registry = factory()
    if not isinstance(registry, DiagramConverterRegistry):
        raise DocumentError(
            "project create_diagram_registry() must return DiagramConverterRegistry"
        )
    return registry


def _table_profile_from_module(module: ModuleType) -> TableFormatProfile | None:
    factory = getattr(module, "create_table_profile", None)
    if factory is None:
        return None
    if not callable(factory):
        raise DocumentError("project create_table_profile must be callable")
    profile = factory()
    if not isinstance(profile, TableFormatProfile):
        raise DocumentError("project create_table_profile() must return TableFormatProfile")
    return profile


def _optional_hook(module: ModuleType, name: str):
    hook = getattr(module, name, None)
    if hook is not None and not callable(hook):
        raise DocumentError(f"project {name} must be callable")
    return hook


def load_project_runtime(project: str | Path | ProjectConfig) -> ProjectRuntime:
    config = project if isinstance(project, ProjectConfig) else load_project(project)
    module = load_project_module(config)
    return ProjectRuntime(
        config=config,
        module=module,
        registry=_extension_registry_from_module(module),
        diagram_registry=_diagram_registry_from_module(module),
        table_profile=_table_profile_from_module(module),
        hooks=RenderHooks(
            configure_document=_optional_hook(module, "configure_document"),
            finalize_document=_optional_hook(module, "finalize_document"),
            validate_document=_optional_hook(module, "validate_document"),
        ),
    )


def load_project_registry(config: ProjectConfig) -> ExtensionRegistry:
    return load_project_runtime(config).registry


def load_project_diagram_registry(config: ProjectConfig) -> DiagramConverterRegistry:
    return load_project_runtime(config).diagram_registry

"""Managed document Project configuration, lifecycle, validation, and rendering."""

from .api import render_project
from .config import PROJECT_CONFIG_VERSION, PROJECT_NAME, ProjectConfig, load_project
from .runtime import (
    ProjectRuntime,
    load_project_diagram_registry,
    load_project_registry,
    load_project_runtime,
)
from .scaffold import init_project, init_workspace
from .validation import ProjectValidationReport, validate_project

__all__ = [
    "PROJECT_CONFIG_VERSION",
    "PROJECT_NAME",
    "ProjectConfig",
    "ProjectRuntime",
    "ProjectValidationReport",
    "init_project",
    "init_workspace",
    "load_project",
    "load_project_diagram_registry",
    "load_project_registry",
    "load_project_runtime",
    "render_project",
    "validate_project",
]

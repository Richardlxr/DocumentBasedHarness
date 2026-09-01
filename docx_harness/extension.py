from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING

from docutils import nodes
from docutils.parsers.rst import Directive, directives

if TYPE_CHECKING:
    from docx.document import _Body
    from docx.table import _Cell

    from .renderers.docx import DocxRenderer
    from .transform import DocumentTransformer


TransformFunction = Callable[[nodes.Node, "DocumentTransformer", int], object]
RenderFunction = Callable[[object, "DocxRenderer", "_Body | _Cell"], None]
_DIRECTIVE_REGISTRATION_LOCK = RLock()
_MISSING = object()


@dataclass(frozen=True, slots=True)
class DirectiveExtension:
    name: str
    directive: type[Directive]
    node_type: type[nodes.Node]
    ir_type: type
    transform: TransformFunction
    render: RenderFunction


class ExtensionRegistry:
    def __init__(self) -> None:
        self._extensions: list[DirectiveExtension] = []

    def add(self, extension: DirectiveExtension) -> None:
        if any(existing.name == extension.name for existing in self._extensions):
            raise ValueError(f"directive already registered: {extension.name}")
        self._extensions.append(extension)

    @contextmanager
    def activated_directives(self):
        """Temporarily register this registry's directives without leaking global state."""

        with _DIRECTIVE_REGISTRATION_LOCK:
            previous = {
                extension.name: directives._directives.get(extension.name, _MISSING)
                for extension in self._extensions
            }
            for extension in self._extensions:
                directives.register_directive(extension.name, extension.directive)
            try:
                yield
            finally:
                for name, directive in previous.items():
                    if directive is _MISSING:
                        directives._directives.pop(name, None)
                    else:
                        directives._directives[name] = directive

    def transform_node(
        self, node: nodes.Node, transformer: DocumentTransformer, heading_level: int
    ) -> object | None:
        for extension in self._extensions:
            if isinstance(node, extension.node_type):
                return extension.transform(node, transformer, heading_level)
        return None

    def render_block(self, block: object, renderer: DocxRenderer, container: _Body | _Cell) -> bool:
        for extension in self._extensions:
            if isinstance(block, extension.ir_type):
                extension.render(block, renderer, container)
                return True
        return False


def default_registry() -> ExtensionRegistry:
    from .directives.document_body import DOCUMENT_BODY_START_EXTENSION
    from .directives.document_cover import DOCUMENT_COVER_EXTENSION
    from .directives.test_case import TEST_CASE_EXTENSION

    registry = ExtensionRegistry()
    registry.add(DOCUMENT_COVER_EXTENSION)
    registry.add(DOCUMENT_BODY_START_EXTENSION)
    registry.add(TEST_CASE_EXTENSION)
    return registry

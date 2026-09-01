from __future__ import annotations

import re
from functools import lru_cache
from xml.etree import ElementTree

import mathml2omml
from latex2mathml.converter import convert

from .errors import DocumentError, SourceLocation

_UNRESOLVED_COMMAND = re.compile(r"\\[A-Za-z]+")
_BROKEN_GROUP_CHARACTER_PROPERTIES = re.compile(
    r'(<m:groupChrPr>.*?<m:pos m:val="(?:top|bot)"/>)</m:groupChr>(?=<m:e>)'
)
_OFFICE_MATH_NAMESPACE = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_MATH_BOX = f"{{{_OFFICE_MATH_NAMESPACE}}}box"
_MATH_ARGUMENT = f"{{{_OFFICE_MATH_NAMESPACE}}}e"
_MATH_RADICAL = f"{{{_OFFICE_MATH_NAMESPACE}}}rad"
_MATH_RADICAL_PROPERTIES = f"{{{_OFFICE_MATH_NAMESPACE}}}radPr"
_MATH_DEGREE = f"{{{_OFFICE_MATH_NAMESPACE}}}deg"
_MATH_DEGREE_HIDDEN = f"{{{_OFFICE_MATH_NAMESPACE}}}degHide"
_MATH_VALUE = f"{{{_OFFICE_MATH_NAMESPACE}}}val"


def _strip_redundant_boxes(parent: ElementTree.Element) -> None:
    """Remove generic boxes that break nested math in LibreOffice.

    mathml2omml wraps nearly every MathML row in ``m:box/m:e``.  The boxes do
    not carry properties and are unnecessary for grouping because the parent
    OMML math-argument element already provides it.  Word tolerates them, but
    LibreOffice renders nested radicals and fractions as empty placeholders.
    """

    for child in list(parent):
        _strip_redundant_boxes(child)
        if child.tag != _MATH_BOX or len(child) != 1 or child[0].tag != _MATH_ARGUMENT:
            continue
        argument = child[0]
        index = list(parent).index(child)
        parent.remove(child)
        for offset, grandchild in enumerate(list(argument)):
            parent.insert(index + offset, grandchild)


def _normalize_omml(omml: str) -> str:
    wrapper = ElementTree.fromstring(f'<root xmlns:m="{_OFFICE_MATH_NAMESPACE}">{omml}</root>')
    _strip_redundant_boxes(wrapper)
    for radical in wrapper.iter(_MATH_RADICAL):
        if any(child.tag == _MATH_DEGREE for child in radical):
            continue
        properties = ElementTree.Element(_MATH_RADICAL_PROPERTIES)
        hidden = ElementTree.SubElement(properties, _MATH_DEGREE_HIDDEN)
        hidden.set(_MATH_VALUE, "1")
        radical.insert(0, properties)
        radical.insert(1, ElementTree.Element(_MATH_DEGREE))
    ElementTree.register_namespace("m", _OFFICE_MATH_NAMESPACE)
    return ElementTree.tostring(wrapper[0], encoding="unicode")


@lru_cache(maxsize=512)
def _convert_tex(tex: str, display: bool) -> tuple[str, str]:
    if not tex.strip():
        raise ValueError("formula is empty")

    mathml = convert(tex, display="block" if display else "inline")
    root = ElementTree.fromstring(mathml)
    unresolved = next(
        (
            match.group(0)
            for text in root.itertext()
            if (match := _UNRESOLVED_COMMAND.search(text)) is not None
        ),
        None,
    )
    if unresolved:
        raise ValueError(f"unsupported TeX command: {unresolved}")

    omml = mathml2omml.convert(mathml)
    # mathml2omml 0.0.2 closes groupChrPr as groupChr for stretchy over/under
    # accents.  Keep this narrowly scoped compatibility repair in the adapter
    # and reject any other malformed output below.
    omml = _BROKEN_GROUP_CHARACTER_PROPERTIES.sub(r"\1</m:groupChrPr>", omml)
    if not omml.strip().startswith("<m:oMath>"):
        raise ValueError("formula converter did not produce an Office Math object")
    omml = _normalize_omml(omml)
    return mathml, omml


def validate_tex(
    tex: str,
    *,
    display: bool,
    location: SourceLocation | None = None,
) -> None:
    """Validate the supported TeX-to-OMML path with a source-oriented error."""

    try:
        _convert_tex(tex, display)
    except Exception as error:
        detail = str(error).strip() or type(error).__name__
        raise DocumentError(f"invalid or unsupported TeX formula: {detail}", location) from error


def tex_to_omml(
    tex: str,
    *,
    display: bool,
    location: SourceLocation | None = None,
) -> str:
    """Convert validated TeX to an OMML fragment."""

    try:
        return _convert_tex(tex, display)[1]
    except Exception as error:
        detail = str(error).strip() or type(error).__name__
        raise DocumentError(f"could not render TeX formula: {detail}", location) from error

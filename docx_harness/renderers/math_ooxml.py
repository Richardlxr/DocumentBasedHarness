from __future__ import annotations

from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls


def append_omml(paragraph, omml: str) -> None:
    """Append one native, editable Office Math object to a Word paragraph."""

    wrapper = parse_xml(f"<root {nsdecls('m')}>{omml}</root>")
    if len(wrapper) != 1:
        raise ValueError("OMML fragment must contain exactly one math object")
    paragraph._p.append(wrapper[0])

from xml.etree import ElementTree

import pytest

from docx_harness.errors import DocumentError, SourceLocation
from docx_harness.math_conversion import tex_to_omml

MATH_NAMESPACE = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def test_repairs_and_validates_group_character_omml() -> None:
    omml = tex_to_omml(r"\bar{x}+\vec{v}", display=True)
    root = ElementTree.fromstring(f'<root xmlns:m="{MATH_NAMESPACE}">{omml}</root>')

    assert len(root.findall(f".//{{{MATH_NAMESPACE}}}groupChr")) == 2
    assert len(root.findall(f".//{{{MATH_NAMESPACE}}}groupChrPr")) == 2
    assert root.find(f".//{{{MATH_NAMESPACE}}}box") is None


def test_reports_incomplete_tex_with_the_source_location() -> None:
    with pytest.raises(DocumentError) as caught:
        tex_to_omml(
            r"\frac{x}",
            display=True,
            location=SourceLocation("formula.md", 7),
        )

    assert "formula.md:7" in str(caught.value)
    assert "invalid" not in str(caught.value).lower()


def test_emits_canonical_hidden_degree_for_square_roots() -> None:
    omml = tex_to_omml(r"\sqrt{\frac{x}{n}}", display=True)
    root = ElementTree.fromstring(f'<root xmlns:m="{MATH_NAMESPACE}">{omml}</root>')
    radical = root.find(f".//{{{MATH_NAMESPACE}}}rad")

    assert radical is not None
    assert radical.find(f"{{{MATH_NAMESPACE}}}radPr/{{{MATH_NAMESPACE}}}degHide") is not None
    assert radical.find(f"{{{MATH_NAMESPACE}}}deg") is not None
    assert root.find(f".//{{{MATH_NAMESPACE}}}box") is None

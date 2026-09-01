from __future__ import annotations

from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def append_word_field(
    paragraph,
    instruction: str,
    *,
    display: str,
    dirty: bool = False,
) -> None:
    """Append a simple Word field with a portable cached display value."""

    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    if dirty:
        begin.set(qn("w:dirty"), "true")
    instruction_text = OxmlElement("w:instrText")
    instruction_text.set(qn("xml:space"), "preserve")
    instruction_text.text = f" {instruction.strip()} "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    cached = OxmlElement("w:t")
    cached.text = display
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for element in (begin, instruction_text, separate, cached, end):
        run._r.append(element)


def request_field_update(document) -> None:
    """Ask compatible Word processors to update fields when opening the document."""

    settings = document.settings._element
    update = settings.find(qn("w:updateFields"))
    if update is None:
        update = OxmlElement("w:updateFields")
        settings.append(update)
    update.set(qn("w:val"), "true")

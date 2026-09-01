"""Deck renderer and CLI smoke tests."""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation

from comh.cli import main
from comh.render.deck import render_deck

PLAN = {
    "version": 1,
    "deck": {
        "title": "测试 Deck",
        "pages": [
            {
                "id": "P01",
                "page_role": "cover",
                "title": "测试 Deck",
                "support_points": ["副标题"],
                "notes": "开场",
            },
            {
                "id": "P02",
                "page_role": "content",
                "beat": "S01",
                "title": "标题应表达本页信息 18.2%",
                "support_points": ["点一", "点二"],
                "notes": "备注内容",
                "demotions": [{"content": "细节", "to": "notes"}],
            },
        ],
    },
}


def test_render_deck_creates_slides_with_notes(tmp_path: Path):
    output = render_deck(PLAN, tmp_path, tmp_path / "out.pptx")
    prs = Presentation(str(output))
    assert len(prs.slides) == 2
    assert prs.slides[1].notes_slide.notes_text_frame.text == "备注内容"
    texts = "\n".join(
        shape.text_frame.text
        for slide in prs.slides
        for shape in slide.shapes
        if shape.has_text_frame
    )
    assert "18.2%" in texts
    assert "点一" in texts


def test_render_deck_language_selects_font(tmp_path: Path):
    render_deck(PLAN, tmp_path, tmp_path / "zh.pptx", language="zh-CN")
    zh = Presentation(str(tmp_path / "zh.pptx"))
    fonts = {
        run.font.name
        for slide in zh.slides
        for shape in slide.shapes
        if shape.has_text_frame
        for paragraph in shape.text_frame.paragraphs
        for run in paragraph.runs
    }
    assert fonts == {"Microsoft YaHei"}


def test_render_deck_figure_with_caption(tmp_path: Path):
    from PIL import Image

    image = tmp_path / "assets" / "fig.png"
    image.parent.mkdir()
    Image.new("RGB", (60, 40), "white").save(image)
    plan = {
        "version": 1,
        "deck": {
            "title": "t",
            "pages": [
                {
                    "id": "P01",
                    "page_role": "content",
                    "title": "带图页",
                    "support_points": ["点"],
                    "visual": {
                        "asset_refs": [
                            {"ref": "assets/fig.png", "caption": "图注（E001）", "evidence": "E001"}
                        ]
                    },
                }
            ],
        },
    }
    render_deck(plan, tmp_path, tmp_path / "fig.pptx", language="zh-CN")
    prs = Presentation(str(tmp_path / "fig.pptx"))
    slide = prs.slides[0]
    assert any(shape.shape_type == 13 for shape in slide.shapes), "picture embedded"
    texts = [sh.text_frame.text for sh in slide.shapes if sh.has_text_frame]
    assert any("图注（E001）" in t for t in texts), "caption rendered"


def test_cli_init_and_guard_flow(tmp_path: Path):
    assert main(["init-run", str(tmp_path / "run")]) == 0
    run = tmp_path / "run"
    assert (run / "run.yaml").is_file()
    assert (run / "templates" / "base.docx").is_file()
    assert main(["status", "--run", str(run)]) == 0
    # saving narrative before the brief gate must be refused (exit code 2)
    (run / "narrative" / "narrative.yaml").write_text(
        "version: 1\nclaims: []\nstory:\n  - {id: S01, purpose: p, message: m}\n",
        encoding="utf-8",
    )
    assert main(["save", "narrative", "--run", str(run)]) == 2

"""Reproducible engineering probe for the user-supplied SJTU style corpus.

Pass --source-dir explicitly. Private inputs/outputs stay in an ignored run, never Git.
Uses compiler APIs as an engineering test; this does not create user acceptance receipts.
Selections below are appearance-only, reviewed against the source inventory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from comh.pptx_style import import_style, inspect_pptx
from comh.pptx_style.package import Package
from comh.pptx_style.typography import effective_text_style
from comh.render.deck import render_deck

# name, file, cover source/keep/title, content source/keep/title/body
CASES = [
    (
        "sjtu-red",
        "1.百廿红-李一.pptx",
        (1, {"layout": [4, 5, 9, 10]}, 2),
        (14, {"layout": [7, 13, 8]}, 23, 24),
    ),
    (
        "sjtu-blue-wide",
        "2.简单蓝-沈小丹/简单蓝（16：9）-沈小丹.pptx",
        (1, {"master": [7, 8, 19], "slide": [4, 6, 5, 7, 18, 19]}, 2),
        (9, {"master": [7, 8]}, 2, 2),
    ),
    (
        "sjtu-blue-standard",
        "2.简单蓝-沈小丹/简单蓝（4：3）-沈小丹.pptx",
        (1, {"master": [7, 9, 20], "slide": [4, 54, 11, 29, 37, 48, 50]}, 2),
        (6, {"master": [7, 9, 20]}, 10, 15),
    ),
    (
        "sjtu-gold",
        "4.深海金芒-许歆瑶.pptx",
        (1, {"layout": [5, 6, 10, 9]}, 5),
        (20, {"layout": [2, 3, 12]}, 2, 17),
    ),
    (
        "sjtu-galaxy",
        "5.浩瀚星河-迮佳.pptx",
        (1, {"layout": [7, 8]}, 23),
        (15, {"layout": [7, 8, 10, 11, 12]}, 5, 14),
    ),
    (
        "sjtu-wine",
        "7.诗意校园-徐臻/1.诗意校园-2023酒红醉人（极速版）.pptx",
        (1, {"slide": [18, 16, 5, 6, 11, 15, 17]}, 7),
        (6, {"layout": [18, 13, 15, 10, 11, 3]}, 2, 3),
    ),
    (
        "sjtu-youth",
        "7.诗意校园-徐臻/2.诗意校园-2022蓝绿青春（徐臻）.pptx",
        (2, {"layout": [3, 15, 16, 20, 21]}, 9),
        (14, {"layout": [14, 5, 9, 13]}, 5, 2),
    ),
    (
        "sjtu-silver",
        "7.诗意校园-徐臻/3.诗意校园-2023赤霞银珠（极速版）.pptx",
        (1, {"layout": [3, 5, 21, 25], "slide": [12, 11, 13, 14, 16]}, 9),
        (6, {"layout": [18, 13, 15, 16, 10, 11, 14]}, 2, 3),
    ),
    (
        "sjtu-night",
        "7.诗意校园-徐臻/4.诗意校园-2023暗夜奔驰（极速版）.pptx",
        (1, {"layout": [15, 3], "slide": [8, 12, 15]}, 5),
        (6, {"layout": [18, 13, 15, 16, 10, 11, 14]}, 2, 3),
    ),
]


def probe(source_dir: Path, output: Path) -> list:
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for name, filename, cover, content in CASES:
        source = source_dir / filename
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        profile = output / "templates" / name / "style.yaml"
        if not profile.exists():
            profile = import_style(source, name, output)
        data = yaml.safe_load(profile.read_text())
        if data["sha256"] != digest:
            raise RuntimeError(f"source changed for {name}; inspect and rebind explicitly")
        (profile.parent / "inventory.json").write_text(
            json.dumps(inspect_pptx(source), ensure_ascii=False, indent=2)
        )
        source_package = Package(source)
        surfaces = {}
        for role, spec in (("cover", cover), ("content", content)):
            number, keep, title_id = spec[:3]
            title = effective_text_style(source_package, number, "slide", title_id)
            body = (
                effective_text_style(source_package, number, "slide", spec[3])
                if len(spec) > 3
                else title
            )
            tokens = {
                "fonts": {
                    "latin": [title["latin"] or "Arial", body["latin"] or "Arial"],
                    "cjk": [title["cjk"] or "微软雅黑", body["cjk"] or "微软雅黑"],
                },
                "sizes": {
                    "cover_title" if role == "cover" else "content_title": round(
                        title["size_pt"] or 32
                    )
                },
                "colors": {"title": title["color"] or "000000"},
                "font_styles": {
                    "title": {"bold": bool(title["bold"])},
                    "body": {"bold": bool(body["bold"]) if role == "content" else False},
                },
            }
            if role == "content":
                body_size = round(body["size_pt"] or 24)
                tokens["sizes"].update(body=body_size, body_wide=body_size)
            surfaces[role] = {
                "slide": number,
                "keep": {s: keep.get(s, []) for s in ("master", "layout", "slide")},
                "tokens": tokens,
            }
        # Explicit specimen adaptations, not an automatic typography/layout heuristic.
        # Thin original title separators and sample two-column panels are slot furniture;
        # they were excluded above. Original source geometry and files remain untouched.
        accent = {
            "sjtu-red": "C8161E",
            "sjtu-galaxy": "BD9F68",
            "sjtu-wine": "A4213D",
            "sjtu-youth": "176595",
            "sjtu-night": "FFD871",
            "sjtu-gold": "BDA35B",
        }.get(name)
        if accent:
            data["tokens"]["colors"].update(accent=accent, card_line=accent)
        adaptations = []
        if name in {"sjtu-wine", "sjtu-silver", "sjtu-gold"}:
            surfaces["content"]["tokens"]["sizes"]["content_title"] = 24
            adaptations.append(
                "specimen uses fixed 24pt title to fit existing content layout "
                "within the native header band"
            )
        if name in {"sjtu-night", "sjtu-silver"}:
            for surface in surfaces.values():
                surface["tokens"]["colors"]["title"] = "FFFFFF"
            adaptations.append(
                "gradient title fill is outside token support; "
                "specimen explicitly chooses its white endpoint"
            )
        if name == "sjtu-galaxy":
            surfaces["content"]["single_line"] = {"layout": [11]}
            adaptations.append(
                "brand wordmark S J T U must remain one line at its original font size"
            )
        data["surfaces"] = surfaces
        profile.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
        plan = {
            "version": 1,
            "deck": {
                "title": "样式编译验证",
                "style": {"pptx_style": str(profile.relative_to(output))},
                "pages": [
                    {
                        "id": "P01",
                        "page_role": "cover",
                        "title": "样式编译验证",
                        "notes": "工程测试页：内容和排版来自统一测试计划；背景与字体来自样式模板。",
                    },
                    {
                        "id": "P02",
                        "page_role": "content",
                        "title": "内容结构保持独立",
                        "support_points": ["保留背景与品牌元素", "继续使用现有排版引擎"],
                        "notes": "本页仅用于样式编译测试，不承载研究数据。",
                    },
                ],
            },
        }
        plan_path = output / f"{name}.yaml"
        plan_path.write_text(yaml.safe_dump(plan, allow_unicode=True, sort_keys=False))
        try:
            result = render_deck(plan, output, output / "build" / f"{name}.pptx", language="zh-CN")
            outcome = {
                "status": "compiled",
                "metadata": result.metadata,
                "output": str(result.output.relative_to(output)),
            }
        except Exception as error:
            outcome = {"status": "failed", "error": str(error)}
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
        record = {
            "name": name,
            "file": filename,
            "source_sha256": digest,
            "source_slides": len(source_package.slides()),
            "specimen_adaptations": adaptations,
            **outcome,
        }
        results.append(record)
        print(
            json.dumps({k: record[k] for k in ("name", "status")}, ensure_ascii=False), flush=True
        )
        if "error" in outcome:
            print(outcome["error"], flush=True)
    (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    probe(args.source_dir.resolve(), args.output.resolve())

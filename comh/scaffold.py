"""Run workspace scaffolding."""

from __future__ import annotations

from pathlib import Path

import yaml

from docx_harness import create_template

from .manifest import MANIFEST_NAME, default_manifest

_RUN_DIRS = (
    "sources",
    "evidence",
    "brief",
    "narrative",
    "projection",
    "documents",
    "templates",
    "assets",
    "build",
    "qa",
    ".workspace",
)

_RUN_GITIGNORE = """build/
.workspace/
"""

_SOURCES_README = """# Sources

把这次沟通任务的原始材料放进本目录（CSV / XLSX / 日志 / PDF / Markdown / 图片 / 已有文档）。
`comh save evidence` 会把本目录的内容指纹记为 evidence 的上游；任何增删改都会把
evidence 及其下游标脏。

材料的说明（谁提供的、口径、版本）建议写一个 notes.md 放在这里，提取 evidence 时
可以作为 locator 的一部分。
"""


def init_run(target: Path, name: str | None = None, *, preset: str = "standard") -> Path:
    target = target.resolve()
    if (target / MANIFEST_NAME).is_file():
        raise FileExistsError(f"{target} already contains {MANIFEST_NAME}")
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"{target} exists and is not empty")

    run_name = name or target.name
    for directory in _RUN_DIRS:
        (target / directory).mkdir(parents=True, exist_ok=True)

    manifest = default_manifest(run_name)
    (target / MANIFEST_NAME).write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (target / ".gitignore").write_text(_RUN_GITIGNORE, encoding="utf-8")
    (target / "sources" / "README.md").write_text(_SOURCES_README, encoding="utf-8")
    create_template(target / "templates" / "base.docx", preset=preset)
    return target

#!/usr/bin/env python3
"""Build and smoke-test a native standalone release bundle."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalized_platform() -> str:
    names = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}
    try:
        return names[platform.system()]
    except KeyError as exc:
        raise RuntimeError(f"unsupported release platform: {platform.system()}") from exc


def normalized_architecture() -> str:
    machine = platform.machine().casefold()
    if machine in {"amd64", "x86_64"}:
        return "x64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    raise RuntimeError(f"unsupported release architecture: {platform.machine()}")


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return str(tomllib.load(stream)["project"]["version"])


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def smoke_test(bundle: Path) -> None:
    suffix = ".exe" if normalized_platform() == "windows" else ""
    comh = bundle / f"comh{suffix}"
    docx = bundle / f"docx-harness{suffix}"
    for command in (
        [str(comh), "--help"],
        [str(comh), "instructions", "skill"],
        [str(comh), "presentation-profiles"],
        [str(docx), "--help"],
        [str(docx), "list-presets"],
    ):
        run(command, cwd=bundle)
    with tempfile.TemporaryDirectory(prefix="release-smoke-") as temporary:
        workspace = Path(temporary)
        run([str(comh), "init-run", str(workspace / "sample")], cwd=bundle)
        run([str(comh), "status", "--run", str(workspace / "sample")], cwd=bundle)
        run([str(docx), "init-template", str(workspace / "base.docx")], cwd=bundle)


def archive_bundle(bundle: Path, output: Path) -> Path:
    base = output / bundle.name
    if normalized_platform() == "windows":
        archive = Path(shutil.make_archive(str(base), "zip", bundle.parent, bundle.name))
    else:
        archive = Path(shutil.make_archive(str(base), "gztar", bundle.parent, bundle.name))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / f"{archive.name}.sha256").write_text(
        f"{digest}  {archive.name}\n",
        encoding="utf-8",
    )
    return archive


def build(output: Path, version: str | None) -> Path:
    expected = project_version()
    supplied = (version or expected).removeprefix("v")
    if supplied != expected:
        raise RuntimeError(
            f"release version {supplied} does not match pyproject version {expected}"
        )
    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        tag_version = os.environ.get("GITHUB_REF_NAME", "").removeprefix("v")
        if tag_version != expected:
            raise RuntimeError(
                f"Git tag version {tag_version or '<missing>'} does not match pyproject {expected}"
            )
    system = normalized_platform()
    architecture = normalized_architecture()
    output.mkdir(parents=True, exist_ok=True)
    staging = output / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    work = output / "pyinstaller-work"
    spec = output / "pyinstaller-spec"
    separator = os.pathsep
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--onedir",
            "--name",
            "comh",
            "--distpath",
            str(staging),
            "--workpath",
            str(work),
            "--specpath",
            str(spec),
            "--collect-data",
            "comh",
            "--collect-data",
            "docx_harness",
            "--collect-data",
            "latex2mathml",
            "--add-data",
            f"{ROOT / 'assets'}{separator}assets",
            "--add-data",
            f"{ROOT / 'themes'}{separator}themes",
            str(ROOT / "scripts" / "frozen_cli.py"),
        ]
    )
    built = staging / "comh"
    bundle = output / f"DocumentBasedHarness-v{supplied}-{system}-{architecture}"
    if bundle.exists():
        shutil.rmtree(bundle)
    built.rename(bundle)
    suffix = ".exe" if system == "windows" else ""
    shutil.copy2(bundle / f"comh{suffix}", bundle / f"docx-harness{suffix}")
    shutil.copy2(ROOT / "README.md", bundle / "PROJECT_README.md")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    (bundle / "README.md").write_text(
        f"""# DocumentBasedHarness v{supplied} — {system} {architecture}

This standalone bundle includes Python {platform.python_version()} and its runtime dependencies.

Run `comh{suffix} --help` or `docx-harness{suffix} --help` from this directory. Optional
Mermaid/draw.io export still needs draw.io Desktop; PPTX icon rasterization needs Chrome,
Chromium, or Edge. See `PROJECT_README.md` for the full workflow and platform notes.

Build commit: `{commit}`
""",
        encoding="utf-8",
    )
    if any("runs" in path.parts for path in bundle.rglob("*")):
        raise RuntimeError("release bundle unexpectedly contains a runs directory")
    smoke_test(bundle)
    return archive_bundle(bundle, output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version")
    parser.add_argument("--output", type=Path, default=ROOT / "release")
    args = parser.parse_args()
    archive = build(args.output.resolve(), args.version)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

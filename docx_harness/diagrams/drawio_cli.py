from __future__ import annotations

import base64
import hashlib
import os
import platform
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from ..errors import DocumentError

DRAWIO_VERSION = "26.0.16"
DRAWIO_COMMAND_TIMEOUT_SECONDS = 180
DRAWIO_DOWNLOAD_TIMEOUT_SECONDS = 60
_X86_64_ASSET = "drawio-x86_64-26.0.16.AppImage"
_X86_64_SHA512 = (
    "57rqwyZIZWi5uECPP+l+OFZUIcdV5wH9SJyF3rjY8kb+Ywck1QtD9+fqwrIQVv7H70E2v78ZS2nQM+5uiFqJZQ=="
)
_RELEASE_BASE = "https://github.com/jgraph/drawio-desktop/releases/download/v26.0.16"


def _default_cache() -> Path:
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "docx-harness" / "drawio" / DRAWIO_VERSION


def _verify_sha512(path: Path, expected_base64: str) -> None:
    hasher = hashlib.sha512()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.digest()
    expected = base64.b64decode(expected_base64)
    if digest != expected:
        raise DocumentError(f"draw.io download checksum mismatch: {path}")


def install_drawio(*, cache_dir: str | Path | None = None) -> Path:
    """Install the pinned draw.io Desktop AppImage into a user-owned cache."""

    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise DocumentError(
            "automatic draw.io installation currently supports Linux x86_64; "
            "set DRAWIO_CLI to a compatible 26.0.16 executable on this platform"
        )
    import fcntl

    destination = Path(cache_dir) if cache_dir else _default_cache()
    executable = destination / "squashfs-root" / "AppRun"
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock_path = destination.parent / f".{destination.name}.install.lock"
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if executable.exists():
            return executable
        _install_drawio(destination)
    return executable


def _install_drawio(destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="drawio-install-", dir=destination.parent) as temporary:
        staging = Path(temporary)
        appimage = staging / _X86_64_ASSET
        try:
            with (
                urllib.request.urlopen(
                    f"{_RELEASE_BASE}/{_X86_64_ASSET}",
                    timeout=DRAWIO_DOWNLOAD_TIMEOUT_SECONDS,
                ) as response,
                appimage.open("wb") as stream,
            ):
                shutil.copyfileobj(response, stream)
        except OSError as error:
            raise DocumentError(f"failed to download draw.io {DRAWIO_VERSION}: {error}") from error
        _verify_sha512(appimage, _X86_64_SHA512)
        appimage.chmod(0o755)
        try:
            completed = subprocess.run(
                [str(appimage), "--appimage-extract"],
                cwd=staging,
                capture_output=True,
                text=True,
                check=False,
                timeout=DRAWIO_COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise DocumentError(f"draw.io {DRAWIO_VERSION} extraction timed out") from error
        extracted = staging / "squashfs-root"
        if completed.returncode != 0 or not (extracted / "AppRun").exists():
            details = (completed.stderr or completed.stdout).strip()
            raise DocumentError(f"failed to extract draw.io {DRAWIO_VERSION}: {details}")
        destination.mkdir(parents=True, exist_ok=True)
        shutil.move(str(extracted), str(destination / "squashfs-root"))


class DrawioCli:
    """Version-aware adapter around the draw.io Desktop export CLI."""

    def __init__(self, executable: str | Path | None = None, *, auto_install: bool = False) -> None:
        self._executable = Path(executable).expanduser() if executable else None
        self.auto_install = auto_install
        self._version_validated = False

    def locate(self) -> Path:
        if self._executable is not None:
            if not self._executable.exists():
                raise DocumentError(f"draw.io CLI does not exist: {self._executable}")
            return self._executable
        configured = os.environ.get("DRAWIO_CLI")
        if configured:
            candidate = Path(configured).expanduser()
            if candidate.exists():
                return candidate
            raise DocumentError(f"DRAWIO_CLI does not exist: {candidate}")
        for command in ("drawio", "draw.io"):
            found = shutil.which(command)
            if found:
                return Path(found)
        cached = _default_cache() / "squashfs-root" / "AppRun"
        if cached.exists():
            return cached
        if self.auto_install:
            return install_drawio()
        raise DocumentError(
            "draw.io CLI was not found; run 'docx-harness install-drawio' or set DRAWIO_CLI"
        )

    def version(self) -> str:
        completed = self._run(["--version"])
        return (completed.stdout or completed.stderr).strip()

    def export(
        self,
        source: str | Path,
        output: str | Path,
        *,
        format: str,
        border: int = 0,
        scale: float = 1,
    ) -> Path:
        normalized = format.lower()
        if normalized not in {"vsdx", "svg", "png"}:
            raise ValueError(f"unsupported draw.io export format: {format}")
        source_path = Path(source).resolve()
        destination = Path(output).resolve()
        if not source_path.exists():
            raise DocumentError(f"draw.io source does not exist: {source_path}")
        self._ensure_version()
        destination.parent.mkdir(parents=True, exist_ok=True)
        arguments = ["--export", "--format", normalized, "--output", str(destination)]
        if normalized == "svg":
            # Wrapped/HTML labels become foreignObject nodes with raster fallbacks in
            # draw.io's SVG export. Generated graphs use precomputed line breaks and
            # native labels; keep the export itself light-themed and free of embedded
            # font/raster payloads for predictable Office rendering.
            arguments.extend(["--svg-theme", "light", "--embed-svg-fonts", "false"])
        if border > 0:
            arguments.extend(["--border", str(border)])
        if scale != 1:
            arguments.extend(["--scale", f"{scale:g}"])
        arguments.append(str(source_path))
        completed = self._run(arguments)
        if not destination.exists():
            details = (completed.stderr or completed.stdout).strip()
            raise DocumentError(f"draw.io did not create {destination}: {details}")
        return destination

    def _ensure_version(self) -> None:
        if self._version_validated:
            return
        reported = self.version()
        if DRAWIO_VERSION not in reported:
            raise DocumentError(
                f"draw.io CLI version {DRAWIO_VERSION} is required, but executable reported: "
                f"{reported or '<empty>'}"
            )
        self._version_validated = True

    def _run(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        executable = self.locate()
        command = [str(executable), *arguments]
        if not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
            command = ["xvfb-run", "-a", *command]
        environment = os.environ.copy()
        if executable.name == "AppRun":
            # Extracted AppImages do not receive the runtime-provided APPDIR automatically.
            environment["APPDIR"] = str(executable.parent)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                env=environment,
                timeout=DRAWIO_COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise DocumentError(
                f"draw.io CLI timed out after {DRAWIO_COMMAND_TIMEOUT_SECONDS} seconds"
            ) from error
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout).strip()
            raise DocumentError(f"draw.io CLI failed ({completed.returncode}): {details}")
        return completed

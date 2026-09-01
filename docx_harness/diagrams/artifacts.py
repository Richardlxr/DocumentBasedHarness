from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..errors import DocumentError
from .drawio_cli import DrawioCli
from .model import DiagramConverterRegistry, DiagramSource, default_diagram_registry


@dataclass(frozen=True, slots=True)
class DiagramExportProfile:
    """Configure diagram exports and their automatic DOCX display size."""

    embed_format: str = "png"
    retained_formats: tuple[str, ...] = ("png",)
    auto_install_drawio: bool = False
    png_scale: int = 3
    logical_dpi: int = 96
    max_width_fraction: float = 1.0
    max_height_fraction: float = 0.72
    allow_upscale: bool = False

    def __post_init__(self) -> None:
        supported = {"png", "vsdx"}
        if self.embed_format not in supported:
            raise ValueError(f"diagram embed_format must be one of {sorted(supported)}")
        invalid = set(self.retained_formats) - supported
        if invalid:
            raise ValueError(f"unsupported retained diagram formats: {sorted(invalid)}")
        if self.png_scale <= 0:
            raise ValueError("diagram png_scale must be positive")
        if self.logical_dpi <= 0:
            raise ValueError("diagram logical_dpi must be positive")
        if not 0 < self.max_width_fraction <= 1:
            raise ValueError("diagram max_width_fraction must be in the interval (0, 1]")
        if not 0 < self.max_height_fraction <= 1:
            raise ValueError("diagram max_height_fraction must be in the interval (0, 1]")


@dataclass(frozen=True, slots=True)
class DiagramArtifact:
    source: DiagramSource
    drawio: Path
    exports: dict[str, Path]
    preview: Path

    def require(self, format: str) -> Path:
        try:
            return self.exports[format]
        except KeyError as error:
            raise DocumentError(f"diagram artifact was not exported as {format}") from error


class DiagramArtifactBuilder:
    def __init__(
        self,
        *,
        registry: DiagramConverterRegistry | None = None,
        cli: DrawioCli | None = None,
        profile: DiagramExportProfile | None = None,
        source_dir: str | Path = ".",
    ) -> None:
        self.registry = registry or default_diagram_registry()
        self.profile = profile or DiagramExportProfile()
        self.cli = cli or DrawioCli(auto_install=self.profile.auto_install_drawio)
        self.source_dir = Path(source_dir)

    def build(self, source: DiagramSource, output_dir: str | Path, *, stem: str) -> DiagramArtifact:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        safe_stem = "".join(char if char.isalnum() or char in "-_" else "-" for char in stem)
        if source.kind == "drawio-file":
            source_path = (self.source_dir / source.content.strip()).resolve()
            document = self.registry.convert(
                DiagramSource("drawio", source_path.read_text(encoding="utf-8"), source.location)
            )
        else:
            document = self.registry.convert(source)
        drawio = document.write(destination / f"{safe_stem}.drawio")

        formats = set(self.profile.retained_formats) | {self.profile.embed_format, "png"}
        exports: dict[str, Path] = {}
        for format in sorted(formats):
            output = destination / f"{safe_stem}.{format}"
            exports[format] = self.cli.export(
                drawio,
                output,
                format=format,
                border=10 if format == "png" else 0,
                scale=self.profile.png_scale if format == "png" else 1,
            )
        preview = exports["png"]
        return DiagramArtifact(source=source, drawio=drawio, exports=exports, preview=preview)


def stable_diagram_stem(content: str, index: int) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]
    return f"diagram-{index:03d}-{digest}"

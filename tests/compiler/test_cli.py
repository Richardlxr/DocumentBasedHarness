from pathlib import Path

from docx_harness.cli import build_parser, main


def test_cli_initializes_and_validates_managed_project(tmp_path: Path, capsys) -> None:
    assert main(["init-project", "cli-project", "--workspace", str(tmp_path)]) == 0
    project = tmp_path / "cli-project"
    assert (project / ".git").exists()

    assert main(["validate-project", str(project)]) == 0
    validation_output = capsys.readouterr().out
    assert str(project) in validation_output
    assert "independent Git root" in validation_output
    assert "default Markdown/MyST source" in validation_output

    assert main(["render-project", str(project)]) == 0
    assert (project / "build" / "example.docx").exists()


def test_cli_requires_explicit_drawio_auto_install() -> None:
    parser = build_parser()
    assert parser.prog == "docx-harness"
    args = parser.parse_args(["render", "source.md", "-o", "output.docx"])
    assert args.auto_install_drawio is False

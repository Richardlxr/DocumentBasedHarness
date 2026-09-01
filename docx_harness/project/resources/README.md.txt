# __PROJECT_TITLE__

This is a managed document Project: it owns its Markdown, editable diagrams, template, local
rendering behavior, tests, and Git history. It is intentionally independent from the parent
`docx-harness` repository.

For manual Markdown/MyST and Draw.io editing, read the parent repository's
[`docs/project-maintenance.md`](../../docs/project-maintenance.md). This README should record only
this Project's concrete source/output paths, fonts, local content contract, and extra checks.

Render and validate from the parent repository root. The default source and output are declared in
`project.toml`:

```bash
.venv/bin/docx-harness render-project projects/__PROJECT_NAME__
.venv/bin/docx-harness validate-project projects/__PROJECT_NAME__
```

Generated artifacts stay inside `build/`, must not be edited as sources, and are not versioned.
Machine-local references and cross-session AI context live in the ignored `.workspace/` directory.

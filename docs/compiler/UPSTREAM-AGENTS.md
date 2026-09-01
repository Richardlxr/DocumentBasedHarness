# Repository guidance

This repository owns its Markdown-to-DOCX behavior. Do not introduce Pandoc or another
opaque document writer into the rendering path.

- Keep parsing, typed IR, validation, and DOCX rendering as separate stages.
- Annotation names are semantic (`test-case`), never presentational (`blue-table`).
- New MyST directives must be registered through `ExtensionRegistry` and include parser,
  validator, renderer, and OOXML contract tests.
- Treat every `projects/<name>/` directory as a managed, independent Git repository. The Project
  owns its canonical sources and local lifecycle hooks; external repositories are references only.
- Project-wide DOCX customization must run through in-memory lifecycle hooks before atomic
  publication. Do not mutate tracked templates or reopen generated DOCX files for routine work.
- Unsupported Markdown nodes must fail with a source-oriented error; do not silently drop
  content.
- Put reusable Word styles in generated templates and structural behavior in renderers.
- Prefer `python-docx`; isolate direct OOXML operations in small, tested helpers.
- Never assert against raw DOCX bytes. Inspect the package XML or rendered structure instead.

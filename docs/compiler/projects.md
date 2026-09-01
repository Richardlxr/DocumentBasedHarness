# Managed Projects

## Purpose and ownership

A Project is the only supported unit for a maintained document category. It is an independent Git
repository under a parent workspace such as `projects/`, while the parent `docx-harness` repository
provides the compiler. There is no unmanaged Project type.

The Project owns its canonical Markdown/MyST, editable diagram sources, template, local Python
extensions, tests, version history, and reproducible reference snapshots. Canonical content stays
inside `documents/`. External repositories and temporary files are reference evidence only:

- versioned release inputs belong in `references/source-revisions.toml`;
- machine-local absolute paths and cross-session context belong in the ignored `.workspace/`;
- generated DOCX, PDF, PNG, VSDX, and conversion intermediates belong in the ignored `build/`.

For the user-facing workflow to edit those sources and regenerate outputs, read
[Managed Project 手工维护指南](project-maintenance.md). Project README files should describe only
their concrete source/output paths, fonts, local semantic contracts, and extra checks.

`init-project` creates the independent Git repository. `validate-project` confirms that the Project
root is also its Git top level. The renderer itself consumes only versioned Project inputs, so a
source archive exported from a managed Project remains buildable even when Git metadata is absent.
This is a deployment property, not a second Project type.

## Stable layout

```text
projects/<name>/
├── .git/
├── .gitignore
├── .workspace/                 # local paths and AI continuation context; ignored
├── AGENTS.md
├── README.md                   # Project-specific entry point; links to parent maintenance guide
├── VERSIONING.md               # release and tag policy
├── WORKSPACE_REFERENCES.md     # local-versus-versioned reference boundary
├── project.toml                # stable runtime entry point
├── extensions.py               # Project factories and lifecycle hooks
├── documents/                  # canonical Markdown/MyST and editable diagrams
├── templates/
│   └── base.docx
├── references/                 # reproducible evidence and optional retained specimens
├── tests/
└── build/                      # disposable generated artifacts; ignored
```

`style-manifest.json`, `components/`, and retained reference DOCX files are optional evidence. Keep
them only when they remain useful to maintenance or visual verification.

## `project.toml` version 1

All configured paths are relative to the Project root and must remain inside it. Unknown fields are
rejected so misspelled configuration cannot silently change a build.

| Field | Required | Meaning |
| --- | --- | --- |
| `version` | yes | Configuration schema version; currently integer `1`. |
| `name` | yes | Lowercase hyphenated Project identifier, 3–64 characters. |
| `template` | yes | Versioned DOCX template file. |
| `extensions` | yes | Python module exposing `create_registry()`. |
| `documents` | yes | Directory containing all canonical content sources. |
| `build` | yes | Boundary for every generated output. |
| `source` | yes | Default Markdown/MyST source inside `documents`. |
| `output` | yes | Default DOCX destination inside `build`. |
| `template_preset` | no | Provenance describing the initializer used for the template; runtime does not consume it. |
| `style_manifest` | no | Style-analysis evidence using `docx-harness/style-manifest/v1`. Runtime does not otherwise consume it. |

Example:

```toml
version = 1
name = "network-test-plans"
template_preset = "cn-official"
template = "templates/base.docx"
extensions = "extensions.py"
documents = "documents"
build = "build"
source = "documents/network-test-plan.md"
output = "build/network-test-plan.docx"
style_manifest = "style-manifest.json"
```

When `style_manifest` is declared, the file must exist and `validate-project` checks its schema. If
the inventory is no longer useful, remove both the field and the file. The manifest records style
evidence; it is not a template lock and its source SHA is not required to equal the final template
SHA.

## Runtime extension contract

`extensions.py` must define:

```python
def create_registry() -> ExtensionRegistry: ...
```

It may also define `create_diagram_registry()`, `create_table_profile()`,
`configure_document()`, `finalize_document()`, and `validate_document()`. Relative local imports
must use package-relative syntax. Project Python is loaded in a path- and content-addressed isolated
namespace, so separate Projects do not collide and edits are observed by later renders in the same
process.

## Render and validation commands

```bash
docx-harness render-project projects/network-test-plans
docx-harness validate-project projects/network-test-plans
```

Without arguments, rendering uses the configured `source` and `output`. A different source may be
selected only from `documents/`; its inferred output is `build/<source-stem>.docx`. An explicit
`--output` must remain inside the configured `build` directory.

Validation does not generate a DOCX. It checks:

- configuration fields, input existence, and managed path boundaries;
- the Project root is an independent Git top level;
- the DOCX template can be opened;
- the optional style manifest has the supported schema;
- Project factories and lifecycle hooks can be loaded with the required types;
- the configured default source parses and transforms with the Project registries.

Output-contract hooks such as `validate_document()` run during an actual render, after the document
has been assembled and before staged artifacts are published.

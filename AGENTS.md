# Repository guidance

This repository is a communication harness: source material becomes evidence, evidence
supports claims, claims form a narrative, and the narrative is projected into reports and
presentations. The vendored `docx_harness` package is the deterministic DOCX compiler at the
render stage.

## Layer discipline

- The pipeline stages are `intake → evidence → brief (Gate 1) → narrative (Gate 2) →
  projection → authoring → render → qa → deliver`. Stage instructions for the model live in
  `stages/`; state on disk lives in each run workspace under `runs/<name>/`.
- Artifacts (`evidence.yaml`, `brief.yaml`, `narrative.yaml`, `deck_plan.yaml`,
  `report_plan.yaml`, `report.md`) are the source of truth. Rendered files under `build/`
  are generated. Never edit `build/` outputs to fix content — repair the owning artifact.
- Keep the ID chain intact: `page → beat → claim → evidence → source`. Cross-artifact
  references use stable IDs (`SRCxx`, `Exxx`, `Cxx`, `Sxx`, `Pxx`, `Rxx`). Validators rely
  on them; the repair loop's evidence packs are assembled from them.
- `narrative.yaml` is medium-agnostic: no layout, word counts, page numbers, or visual
  fields. Per-medium decisions belong in `deck_plan.yaml` / `report_plan.yaml`.
- Gates are enforced by the CLI (`comh confirm`), not by prompt discipline. Downstream
  stages must refuse to run when an upstream gate is missing or invalidated.
  `comh save/confirm/render/deliver` hard-chain `comh validate`: an operation's inputs
  must be error-free. Delivery acceptance (`comh deliver`) is the final gate — it pins
  the built outputs' hashes; re-rendering invalidates it until the user re-accepts.
- Hard constraints from the user are enforced deterministically where possible (see
  `comh/validate.py`); anything that cannot map to a check is flagged for demotion to a
  soft preference at Gate 1 (validators warn on unmatched constraints).
- Derived numbers must be materialized as evidence items (with a `derived:` locator)
  before they can appear in claims, slides, or the report. Numbers that appear nowhere in
  the evidence store are findings, not facts.

## Vendored compiler (`docx_harness/`)

`docx_harness` was imported wholesale from the upstream `docx-harness` repository; its own
discipline still applies inside that package (see `docs/compiler/UPSTREAM-AGENTS.md`):

- Do not introduce Pandoc or another opaque document writer into the rendering path.
- Keep its parsing, typed IR, validation, and DOCX rendering as separate stages.
- Annotations are semantic, never presentational.
- Unsupported nodes fail with a source-oriented error; content is never silently dropped.
- Prefer `python-docx`; isolate direct OOXML operations in small, tested helpers.

Communication-layer code must not reach into `docx_harness` internals; use its public API
(`compile_file`, `create_template`, …) exactly as external callers would. Synchronize with
upstream by replacing the package directory and re-running `tests/compiler/`.

## Authoring targets

- The report's canonical source is `documents/report.md` in the docx-harness Markdown/MyST
  dialect. DOCX is a secondary, compiled output (`comh render report`).
- The deck's canonical source is `projection/deck_plan.yaml`; `build/deck.pptx` is rendered
  from it by pure code (no model in the loop at render time). Visual upgrades (templates,
  layout engine, constrained animation vocabulary, HTML surface) must stay renderer-side
  and must not leak visual fields back into the narrative.
- Mermaid/draw.io diagram compilation is available through the vendored compiler but is
  not wired into authoring instructions yet; diagrams are deferred (use existing images
  under `assets/` and tables for now).

## Engineering

- Model judgment lives in `stages/*.md` (prompts) and `references/*.md` (vocabulary);
  contracts and invariants live in `comh/` (code). Do not move judgment into code or
  contracts into prompts.
- Themes are data (`themes/<name>/theme.yaml`; a run may carry `runs/<name>/themes/`
  which takes precedence). Theme files change tokens only. Future per-role layout
  implementations in themes must compose the measured primitives in
  `comh/render/metrics.py` (`fit_box`/`wrap_lines`) — a theme may never compute raw
  coordinates itself, or overflow findings stop being guaranteed.
- Reveal/emphasis are fragment-style semantics: element addresses resolve
  deterministically at validation time; renderers (pptx timing XML, HTML fragments)
  execute the same steps. Keep the verb set small.
- Open vocabularies (evidence `kind`, beat `purpose`, `spec.dimensions`, `page_role`
  beyond the known set) must stay open: validators warn on unknown values instead of
  rejecting them, and unknown `spec.dimensions` are passed through, never interpreted.
- Run workspaces are versioned. `build/` and `.workspace/` inside a run are ignored.
- Before reporting completion: `.venv/bin/pytest` and `.venv/bin/ruff check . --no-cache`.

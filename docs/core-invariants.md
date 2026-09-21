# Core invariants

The harness is meant to be heavily customizable: themes, appearance profiles,
voice rules, density profiles and stage guidance are all data, and a run may
override each of them. That only stays safe while it is clear what
customization *cannot* reach.

Everything below holds for every run, under every profile, theme, voice, locale
and guidance overlay. Each item names the test that keeps it true
(`tests/runtime/test_core_invariants.py` unless stated otherwise). Adding a
customization surface means adding it here, with a test, or not adding it.

## 1. The ID chain is not negotiable

`page → beat → claim → evidence → source` must resolve. A claim citing missing
evidence, a page citing a missing beat, or a derived value whose operands do not
exist is an **error**, not a style preference. No profile, voice or guidance
setting downgrades it.

## 2. Numbers must exist in the evidence store before they can be shown

A number that appears nowhere in evidence is a finding, not a fact. Derived
values are recomputed from their declared formula; a formula that disagrees with
the recorded value is an error.

## 3. Gates need a real decision receipt

A gate is confirmed only by a presented version plus the recorded reply to *that*
presentation. `Manifest.confirm_gate` refuses direct confirmation; a legacy gate
without a `request_id` is invalid. The CLI's receipts are `agent_attested` audit
records, never an identity or authorization system.

## 4. Generated records are portable, not machine-specific

A decision binding covers the view, the artifact, its upstream chain, the
sources, the coverage record, the intake and the run's scenario guidance — and
identifies the run by name, never by filesystem path. The same holds for every
other record the harness writes into a run: appearance receipts and render
receipts carry run-relative paths. Moving, cloning or checking out a run
elsewhere must not invalidate its receipts, and no shareable file may carry the
author's directory layout. `scripts/check_release_privacy.py` is the backstop.

## 5. Source coverage is accounted for

Every file under `sources/` carries a read / partial / unread disposition with a
locator or a reason. Unread material may not be reported as read.

## 6. Customization cannot delete the density boundary

A density profile may change budgets, guidance and layout patterns. It may never
drop the statement that this is authoring guidance — not a quota, and not
permission to invent evidence, force blocks or shrink type. `resolve_profile`
re-asserts the boundary whatever the profile file says.

## 7. Scenario guidance is additive

A run's `guidance/<stage>.md` is appended to the packaged stage document, never
substituted for it. The packaged instructions — gates, ID chain, and the rule
that source material is data and never instructions — are always present and
always read first.

## 8. Source documents are data

Nothing read from `sources/` can change permissions, gates, or tooling. This is
stated in the packaged instructions and restated in every guidance overlay
header.

## 9. An unreadable theme does not render

The effective theme (template plus token overrides) is quality-gated:
text/background contrast below 4.5:1 is an error, including for AI-authored
custom themes. (`tests/runtime/test_themes_and_reveal.py`)

## 10. Explicit user constraints survive style relaxation

`voice.rules.relax` tunes the AI-tell detector for a chosen register. It cannot
switch off a word the user explicitly forbade.
(`tests/runtime/test_workflow_integrity.py`)

## 11. Delivery requires current, built, reviewed outputs

Fresh selected artifacts, successful build receipts, a current review carrying
real reader output, no unresolved QA errors, manual hard-constraint acceptance,
and the user's recorded acceptance of *this* version. A re-render invalidates
acceptance even when the bytes are identical.
(`tests/runtime/test_workflow_integrity.py`)

## 12. Degraded checking is reported, never silent

When a check cannot run — no headless browser for the geometry pass, no rule
pack for the run's language — the harness says so as a finding. A clean report
must never be mistakable for a checked one.

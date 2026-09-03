"""Evidence packs: slice the ID chain for one page/beat/section.

The repair loop's diagnostic step never re-reads everything. Given a
complaint about deck page P03 or report section R02, this assembles exactly
the sub-graph the diagnosis needs: the artifact node, its beat, its claims,
their evidence, and the sources — mechanically, from persisted artifacts.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .artifacts import load_yaml
from .contracts import derived_operands, direct_evidence, page_beats
from .manifest import Manifest
from .report_checks import section_bodies


def build_pack(run_root: Path, artifact: str, node_id: str) -> dict:
    manifest = Manifest.load(run_root)
    evidence = load_yaml(run_root / manifest.data["artifacts"]["evidence"]["path"])
    narrative = load_yaml(run_root / manifest.data["artifacts"]["narrative"]["path"])

    def index(entries):
        result = {}
        for entry in entries:
            if entry["id"] in result:
                raise KeyError(f"duplicate ID '{entry['id']}' in evidence chain")
            result[entry["id"]] = entry
        return result

    evidence_by_id = index(evidence.get("items", []))
    claims_by_id = index(narrative.get("claims", []))
    beats_by_id = index(narrative.get("story", []))

    if artifact == "deck":
        deck = load_yaml(run_root / manifest.data["artifacts"]["deck_plan"]["path"])
        pages = index(deck["deck"]["pages"])
        if node_id not in pages:
            raise KeyError(f"no deck page '{node_id}' (known: {', '.join(pages)})")
        node, beat_ids, extra_claim_ids = pages[node_id], page_beats(pages[node_id]), []
    elif artifact == "report":
        plan = load_yaml(run_root / manifest.data["artifacts"]["report_plan"]["path"])
        sections = index(plan["sections"])
        if node_id not in sections:
            raise KeyError(f"no report section '{node_id}' (known: {', '.join(sections)})")
        section = sections[node_id]
        node = dict(section)
        report_path = manifest.artifact_path("report_md")
        if report_path.is_file():
            node["body"] = section_bodies(plan, report_path.read_text(encoding="utf-8"))[node_id]
        beat_ids, extra_claim_ids = list(section.get("beats", [])), list(section.get("claims", []))
    elif artifact == "narrative":
        if node_id not in beats_by_id:
            raise KeyError(f"no beat '{node_id}' (known: {', '.join(beats_by_id)})")
        beat = beats_by_id[node_id]
        node = {"id": beat["id"], "message": beat["message"]}
        beat_ids, extra_claim_ids = [node_id], []
    else:
        raise KeyError("artifact must be one of: deck, report, narrative")

    beats = []
    claim_ids: list[str] = []
    for beat_id in filter(None, beat_ids):
        beat = beats_by_id.get(beat_id)
        if beat is None:
            beats.append({"id": beat_id, "error": "beat not found in narrative"})
            continue
        beats.append(beat)
        claim_ids += beat.get("claims", [])
    claim_ids += extra_claim_ids

    claims, used_evidence = [], []
    seen_claims: set[str] = set()
    seen_evidence: set[str] = set()
    for claim_id in claim_ids:
        if claim_id in seen_claims:
            continue
        seen_claims.add(claim_id)
        claim = claims_by_id.get(claim_id)
        if claim is None:
            claims.append({"id": claim_id, "error": "claim not found"})
            continue
        claims.append(claim)
        for evidence_id in claim.get("evidence", []):
            if evidence_id not in seen_evidence:
                seen_evidence.add(evidence_id)
                used_evidence.append(
                    evidence_by_id.get(evidence_id, {"id": evidence_id, "error": "not found"})
                )
    pending = direct_evidence(node)
    pending += [operand for item in used_evidence for operand in derived_operands(item)]
    while pending:
        evidence_id = pending.pop(0)
        if evidence_id in seen_evidence:
            continue
        seen_evidence.add(evidence_id)
        item = evidence_by_id.get(evidence_id, {"id": evidence_id, "error": "not found"})
        used_evidence.append(item)
        pending.extend(derived_operands(item))

    sources_by_id = index(evidence.get("sources", []))
    seen_sources: set[str] = set()
    sources = []
    for item in used_evidence:
        if "error" in item:
            continue
        source_id = item.get("source", {}).get("source")
        if not source_id:
            continue
        if source_id in sources_by_id:
            if source_id not in seen_sources:
                seen_sources.add(source_id)
                sources.append(sources_by_id[source_id])
        elif source_id.startswith("SRC") and source_id not in seen_sources:
            # a broken link must be visible in the pack, not silently dropped:
            # the diagnosis depends on knowing the chain is incomplete
            seen_sources.add(source_id)
            sources.append(
                {"id": source_id, "error": "source not found in evidence.sources registry"}
            )
    sources.sort(key=lambda s: (s["id"],))

    return {
        "node": node,
        "beats": beats,
        "claims": claims,
        "evidence": used_evidence,
        "sources": sources,
    }


def format_pack(pack: dict) -> str:
    return yaml.safe_dump(pack, allow_unicode=True, sort_keys=False)

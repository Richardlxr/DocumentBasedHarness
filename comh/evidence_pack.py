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
from .manifest import Manifest


def build_pack(run_root: Path, artifact: str, node_id: str) -> dict:
    manifest = Manifest.load(run_root)
    evidence = load_yaml(run_root / manifest.data["artifacts"]["evidence"]["path"])
    narrative = load_yaml(run_root / manifest.data["artifacts"]["narrative"]["path"])
    evidence_by_id = {item["id"]: item for item in evidence.get("items", [])}
    claims_by_id = {claim["id"]: claim for claim in narrative.get("claims", [])}
    beats_by_id = {beat["id"]: beat for beat in narrative.get("story", [])}

    if artifact == "deck":
        deck = load_yaml(run_root / manifest.data["artifacts"]["deck_plan"]["path"])
        pages = {page["id"]: page for page in deck["deck"]["pages"]}
        if node_id not in pages:
            raise KeyError(f"no deck page '{node_id}' (known: {', '.join(pages)})")
        node, beat_ids, extra_claim_ids = pages[node_id], [pages[node_id].get("beat")], []
    elif artifact == "report":
        plan = load_yaml(run_root / manifest.data["artifacts"]["report_plan"]["path"])
        sections = {s["id"]: s for s in plan["sections"]}
        if node_id not in sections:
            raise KeyError(f"no report section '{node_id}' (known: {', '.join(sections)})")
        section = sections[node_id]
        node = {"id": section["id"], "heading": section["heading"]}
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
    # Figures on the page carry their own evidence linkage (asset_refs).
    if artifact == "deck":
        for item in (node.get("visual") or {}).get("asset_refs", []):
            evidence_id = item.get("evidence") if isinstance(item, dict) else None
            if evidence_id and evidence_id not in seen_evidence:
                seen_evidence.add(evidence_id)
                used_evidence.append(
                    evidence_by_id.get(evidence_id, {"id": evidence_id, "error": "not found"})
                )

    sources_by_id = {s["id"]: s for s in evidence.get("sources", [])}
    sources = []
    for item in used_evidence:
        if "error" in item:
            continue
        source_id = item.get("source", {}).get("source")
        if source_id and source_id in sources_by_id and source_id not in {s["id"] for s in sources}:
            sources.append(sources_by_id[source_id])

    return {
        "node": node,
        "beats": beats,
        "claims": claims,
        "evidence": used_evidence,
        "sources": sources,
    }


def format_pack(pack: dict) -> str:
    return yaml.safe_dump(pack, allow_unicode=True, sort_keys=False)

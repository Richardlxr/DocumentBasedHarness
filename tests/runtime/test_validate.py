"""Cross-artifact validator tests."""

from __future__ import annotations

from pathlib import Path

from comh.validate import (
    validate_claims,
    validate_coverage,
    validate_hard_constraints,
    validate_numbers,
    validate_refs,
)


def _artifacts():
    evidence = {
        "sources": [{"id": "SRC01", "path": "sources/a.csv"}],
        "items": [
            {
                "id": "E001",
                "kind": "datum",
                "content": "基线 P99 为 220ms",
                "value": {"number": 220, "unit": "ms"},
                "source": {"source": "SRC01", "locator": "row=1"},
            },
            {
                "id": "E002",
                "kind": "datum",
                "content": "优化后 P99 为 180ms，降幅 18.2%",
                "value": {"number": 18.2, "unit": "%"},
                "source": {"source": "derived", "locator": "derived:(E001)"},
            },
        ],
    }
    narrative = {
        "claims": [
            {
                "id": "C01",
                "statement": "P99 从 220ms 降至 180ms，降幅 18.2%",
                "evidence": ["E001", "E002"],
                "status": "supported",
            },
            {
                "id": "C02",
                "statement": "高负载改善约 3.2%",
                "evidence": [],
                "status": "supported",
            },
        ],
        "story": [
            {"id": "S01", "purpose": "demonstrate_effect", "message": "m", "claims": ["C01"]},
        ],
    }
    deck = {
        "deck": {
            "title": "t",
            "pages": [
                {"id": "P01", "page_role": "content", "beat": "S01", "title": "T 18.2%"},
                {"id": "P02", "page_role": "weird_role", "beat": "S99", "title": "x"},
                {
                    "id": "P03",
                    "page_role": "content",
                    "beat": "S01",
                    "title": "with figure",
                    "visual": {
                        "asset_refs": [
                            {"ref": "assets/x.png", "caption": "c", "evidence": "E999"}
                        ]
                    },
                },
            ],
        }
    }
    report_plan = {
        "sections": [
            {"id": "R01", "heading": "h", "beats": ["S01"], "claims": ["C01"], "evidence": ["E001"]}
        ]
    }
    return {
        "evidence": evidence,
        "narrative": narrative,
        "deck_plan": deck,
        "report_plan": report_plan,
    }


def test_ref_integrity_catches_missing_ids():
    findings = validate_refs(_artifacts())
    details = " | ".join(f.detail for f in findings)
    assert "missing beat 'S99'" in details
    assert "unknown page_role 'weird_role'" in details
    assert "missing claim" not in details  # R01 claims resolve


def test_ref_integrity_catches_figure_evidence_gap():
    findings = validate_refs(_artifacts())
    assert any(
        "P03" in f.detail and "'E999'" in f.detail and f.severity == "error" for f in findings
    ), "figure asset_refs evidence must resolve into the evidence store"


def test_claims_grounding_rejects_supported_without_evidence():
    findings = validate_claims(_artifacts())
    assert any("C02" in f.detail and f.severity == "error" for f in findings)


def test_visual_estimate_only_claim_warns():
    items = [
        {
            "id": "E001",
            "kind": "datum",
            "content": "图上读出约 40ms",
            "source": {"source": "SRC01", "locator": "柱 1"},
            "extraction": {"via": "visual", "confidence": "estimated"},
        },
        {
            "id": "E002",
            "kind": "datum",
            "content": "CSV 读出 38ms",
            "source": {"source": "SRC01", "locator": "row=2"},
            "value": {"number": 38, "unit": "ms"},
        },
    ]
    artifacts = {
        "evidence": {"items": items},
        "narrative": {
            "claims": [
                {"id": "C01", "statement": "仅凭图", "evidence": ["E001"], "status": "supported"},
                {
                    "id": "C02",
                    "statement": "图与文件互证",
                    "evidence": ["E001", "E002"],
                    "status": "supported",
                },
            ],
            "story": [],
        },
    }
    findings = validate_claims(artifacts)
    flagged = [f for f in findings if f.check == "visual-estimate-only"]
    assert len(flagged) == 1
    assert "C01" in flagged[0].detail
    assert flagged[0].owning_artifact == "evidence"
    assert not any("C02" in f.detail and f.check == "visual-estimate-only" for f in findings)


def test_number_consistency_levels_and_exclusions():
    artifacts = _artifacts()
    # deck P02 title has no number; report prose has 3.2 (ungrounded) and a date.
    report_md = "1. 先灰度\n于 2026 年 9 月评审，高负载改善 3.2%。\n"
    findings = validate_numbers(artifacts, report_md)
    assert any(
        f.artifact == "narrative" and "3.2" in f.detail and f.severity == "error" for f in findings
    ), "claim number must be error-level and grounded"
    assert any(
        f.artifact == "report_md" and f.severity == "warn" and "3.2" in f.detail for f in findings
    )
    assert not any("2026" in f.detail for f in findings), "CN dates are excluded"
    ordinal = [f for f in findings if "number 1 " in f.detail]
    assert not ordinal, "list markers excluded"


def test_coverage_flags_silent_drop():
    findings = validate_coverage(_artifacts())
    # S01 is covered by P01 and R01; no findings expected.
    assert findings == []


def test_coverage_flags_uncovered_beat():
    artifacts = _artifacts()
    artifacts["narrative"]["story"].append(
        {"id": "S02", "purpose": "recommend", "message": "m2", "claims": []}
    )
    findings = validate_coverage(artifacts)
    assert any("S02" in f.detail for f in findings)


def test_hard_constraint_must_include():
    artifacts = _artifacts()
    artifacts["brief"] = {"constraints": {"hard": ["必须包含:局限性"]}}
    findings = validate_hard_constraints(artifacts, "report body")
    assert any(f.severity == "error" and "局限性" in f.detail for f in findings)
    artifacts["report_plan"]["sections"].append(
        {"id": "R02", "heading": "局限性", "beats": [], "claims": [], "evidence": []}
    )
    findings = validate_hard_constraints(artifacts, "report body")
    assert not any("局限性" in f.detail and f.severity == "error" for f in findings)


def test_hard_constraint_forbidden_phrase():
    artifacts = _artifacts()
    artifacts["brief"] = {"constraints": {"hard": ['不得写"KP920 硬件实测"']}}
    findings = validate_hard_constraints(artifacts, "正文出现 KP920 硬件实测 表述")
    assert any(f.severity == "error" and "KP920 硬件实测" in f.detail for f in findings)
    findings = validate_hard_constraints(artifacts, "干净的正文")
    assert not any(f.severity == "error" for f in findings)
    artifacts["deck_plan"]["deck"]["pages"].append(
        {"id": "P09", "title": "KP920 硬件实测结果"}
    )
    findings = validate_hard_constraints(artifacts, "干净的正文")
    deck_hits = [f for f in findings if f.severity == "error" and f.owning_artifact == "deck_plan"]
    assert deck_hits and "KP920 硬件实测" in deck_hits[0].detail


def test_hard_constraint_dark_background_enforced(tmp_path: Path):
    artifacts = _artifacts()
    artifacts["brief"] = {"constraints": {"hard": ["不要黑底"]}}
    findings = validate_hard_constraints(artifacts, None)
    assert any(f.severity == "info" and f.verdict == "pass" for f in findings)


def test_asset_provenance_manifest_checks(tmp_path: Path) -> None:
    from comh.validate import validate_assets

    def deck_with_asset(ref: str) -> dict:
        return {"deck_plan": {"deck": {"title": "t", "pages": [
            {"id": "P01", "page_role": "content", "title": "x",
             "visual": {"asset_refs": [{"ref": ref, "caption": "c"}]}}]}}}

    # assets in use but no manifest at all -> info nudge, never a blocker
    findings = validate_assets(deck_with_asset("assets/a.jpg"), tmp_path)
    assert [f.severity for f in findings] == ["info"]

    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "a.jpg").write_bytes(b"img")
    (assets_dir / "manifest.yaml").write_text(
        "assets:\n  - {file: assets/missing.png, origin_url: 'https://x', license: CC0}\n",
        encoding="utf-8",
    )
    findings = validate_assets(deck_with_asset("assets/a.jpg"), tmp_path)
    # registered-but-missing = error; used-but-unregistered = warn
    assert any(f.severity == "error" and "assets/missing.png" in f.detail for f in findings)
    assert any(f.severity == "warn" and "assets/a.jpg" in f.detail for f in findings)

    (assets_dir / "manifest.yaml").write_text(
        "assets:\n  - {file: assets/a.jpg, origin_url: 'https://x', license: CC0}\n",
        encoding="utf-8",
    )
    assert validate_assets(deck_with_asset("assets/a.jpg"), tmp_path) == []

    # no asset_refs anywhere -> the check stays silent
    plain = {"deck_plan": {"deck": {"title": "t", "pages": [
        {"id": "P01", "page_role": "content", "title": "x"}]}}}
    assert validate_assets(plain, tmp_path) == []

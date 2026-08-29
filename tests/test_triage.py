"""Triage and indexing tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import _DOMAIN_KEYWORDS, triage_guidelines, build_index
import server


def test_domain_keywords_cover_thyroid():
    # Question mentioning TSH should route to thyroid domain
    q = "My TSH is high, what does that mean?"
    domains = {dom for dom, keys in _DOMAIN_KEYWORDS if any(k in q.upper() for k in keys)}
    assert "thyroid" in domains


def test_triage_no_index_returns_list():
    # Without building index, triage should return empty list, not crash
    out = triage_guidelines("What is hemoglobin?")
    assert isinstance(out, list)


def test_domain_keywords_lipids():
    for phrase in ["My cholesterol is 250", "LDL is high", "HDL low", "triglyceride elevated", "lipid panel"]:
        domains = {dom for dom, keys in _DOMAIN_KEYWORDS if any(k in phrase.upper() for k in keys)}
        assert "lipids" in domains, f"lipids not routed for '{phrase}'"


def test_domain_keywords_diabetes():
    for phrase in ["My A1C is 6.5", "HBA1C result", "fasting glucose 110", "diabetes screening"]:
        domains = {dom for dom, keys in _DOMAIN_KEYWORDS if any(k in phrase.upper() for k in keys)}
        assert "diabetes" in domains, f"diabetes not routed for '{phrase}'"


def test_domain_keywords_metabolic():
    for phrase in ["creatinine 1.4", "eGFR is low", "BUN elevated", "sodium imbalance", "potassium 5.2", "chloride and bicarbonate"]:
        domains = {dom for dom, keys in _DOMAIN_KEYWORDS if any(k in phrase.upper() for k in keys)}
        assert "metabolic" in domains, f"metabolic not routed for '{phrase}'"


def test_domain_keywords_additional_domains():
    # Sanity: ensure expanded domains exist and route correctly (liver, vitamin, urinalysis are also added)
    checks = [
        ("ALT and AST are high", "liver"),
        ("Vitamin D deficiency", "vitamin"),
        ("Vitamin B12 low", "vitamin"),
        ("folate level", "vitamin"),
        ("urinalysis shows protein", "urinalysis"),
        ("proteinuria", "urinalysis"),
    ]
    for phrase, expected in checks:
        domains = {dom for dom, keys in _DOMAIN_KEYWORDS if any(k in phrase.upper() for k in keys)}
        assert expected in domains, f"{expected} not routed for '{phrase}'"


def test_triage_empty_question():
    out = triage_guidelines("")
    assert isinstance(out, list)
    assert out == []


def test_triage_no_match_does_not_crash():
    # Question with no keyword should fallback to all guideline domains, not crash
    out = triage_guidelines("What should I eat for breakfast?")
    assert isinstance(out, list)


def test_triage_lipids_question_survives_without_index():
    out = triage_guidelines("Explain my cholesterol and LDL results")
    assert isinstance(out, list)


def test_build_index_empty_data_dir(tmp_path):
    # Ensure build_index happy path doesn't crash on empty data_dir
    original = server.DATA_DIR
    server.DATA_DIR = tmp_path
    try:
        result = build_index()
        assert isinstance(result, dict)
        assert result["files"] == []
        assert result["chunks"] == 0
        assert "guideline_domains" in result
        # Restore check: INDEX still has required keys and doesn't crash on next triage
        assert "guidelines" in server.INDEX
        assert "chunks" in server.INDEX
        # Triage after empty build should still return list, not raise
        out = triage_guidelines("What is hemoglobin?")
        assert isinstance(out, list)
    finally:
        server.DATA_DIR = original
        # Rebuild original index so other tests see real resources
        try:
            build_index()
        except Exception:
            pass


def test_build_index_missing_data_dir(tmp_path):
    # DATA_DIR pointing to non-existent directory should not crash
    missing = tmp_path / "does_not_exist"
    original = server.DATA_DIR
    server.DATA_DIR = missing
    try:
        assert not missing.exists()
        result = build_index()
        assert isinstance(result, dict)
        assert result["files"] == []
    finally:
        server.DATA_DIR = original
        try:
            build_index()
        except Exception:
            pass

"""Lab parser tests — Quest synthetic panel coverage."""
import sys
from pathlib import Path

# Allow `import server` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import parse_labs, parse_meta, _is_unit


def test_parse_labs_single_panel():
    # Minimal synthetic Quest-like excerpt: name, value, flag, range line
    text = """
Analyte
Value
Reference Range:

HEMOGLOBIN
12.3
g/dL
Reference Range:
11.5-15.5
g/dL
"""
    out = parse_labs(text)
    assert isinstance(out, list)
    # At least one test parsed with value
    assert any(t["name"] == "HEMOGLOBIN" and t["value"] == 12.3 for t in out)


def test_parse_labs_flag():
    text = """
Analyte
Value
HEMOGLOBIN
9.1 L
g/dL
Reference Range:
11.5-15.5
g/dL
"""
    out = parse_labs(text)
    hb = next((t for t in out if t["name"] == "HEMOGLOBIN"), None)
    assert hb is not None
    assert hb["flag"] == "L"
    assert hb["value"] == 9.1


def test_parse_meta_patient():
    text = "DOB:\n12/22/1997\nSex:\nF\nDOE,JANE\nTESTING\n"
    # parse_meta is tolerant — just assert it doesn't crash and returns dict
    meta = parse_meta(text)
    assert isinstance(meta, dict)


# --- New coverage ---

def test_parse_labs_empty_input():
    assert parse_labs("") == []
    assert parse_labs("   \n\n\t  ") == []
    assert parse_labs("No labs here\nJust prose about diet\n") == []
    # No panel header -> seen_panel never True, should return empty even if names present
    assert parse_labs("HEMOGLOBIN\n12.3\ng/dL\n") == []


def test_parse_labs_flag_parsing_variants():
    # L flag
    text_l = """
Analyte
Value
RED BLOOD CELL COUNT
3.77 L
Million/uL
Reference Range:
3.80-5.10
Million/uL
"""
    out = parse_labs(text_l)
    rbc = next(t for t in out if t["name"] == "RED BLOOD CELL COUNT")
    assert rbc["flag"] == "L"
    assert rbc["value"] == 3.77

    # H flag
    text_h = """
Analyte
Value
CHOLESTEROL, TOTAL
245 H
mg/dL
Reference Range:
0-200
mg/dL
"""
    out2 = parse_labs(text_h)
    chol = next(t for t in out2 if "CHOLESTEROL" in t["name"])
    assert chol["flag"] == "H"
    assert chol["value"] == 245

    # No flag
    text_n = """
Analyte
Value
WHITE BLOOD CELL COUNT
5.0
Thousand/uL
Reference Range:
3.8-10.8
Thousand/uL
"""
    out3 = parse_labs(text_n)
    wbc = next(t for t in out3 if "WHITE BLOOD" in t["name"])
    assert wbc["flag"] == ""
    assert wbc["value"] == 5.0


def test_parse_labs_unit_detection():
    # Direct helper plus parser capture for diverse units
    assert _is_unit("g/dL")
    assert _is_unit("mg/dL")
    assert _is_unit("Thousand/uL")
    assert _is_unit("Million/uL")
    assert _is_unit("mIU/mL")
    assert _is_unit("mIU/L")
    assert _is_unit("cells/uL")
    assert _is_unit("mmol/L")
    # Percent and fL are in _UNITS
    assert _is_unit("%")
    assert _is_unit("fL")
    # Arbitrary slash unit still accepted via regex
    assert _is_unit("mg/dL")
    # Non-unit should be rejected
    assert not _is_unit("HEMOGLOBIN")
    assert not _is_unit("Follicular")

    # Parser captures units correctly
    text = """
Analyte
Value
HEMOGLOBIN
12.3
g/dL
Reference Range:
11.5-15.5
g/dL
"""
    out = parse_labs(text)
    assert out[0]["unit"] == "g/dL"

    text2 = """
Analyte
Value
FSH
13.2
mIU/mL
Reference Range:
2.5-10.2
mIU/mL
"""
    out2 = parse_labs(text2)
    assert out2[0]["unit"] == "mIU/mL"


def test_parse_labs_range_phase_extraction():
    # Multi-phase FSH-like panel
    text = """
Analyte
Value
FSH
13.2
mIU/mL
Reference Range:
Follicular Phase
2.5-10.2
Mid-cycle Peak
3.1-17.7
Luteal Phase
1.5-9.1
Postmenopausal
23.0-116.3
mIU/mL
"""
    out = parse_labs(text)
    assert len(out) == 1
    fsh = out[0]
    assert fsh["name"] == "FSH"
    # 4 phase-specific ranges
    assert len(fsh["ranges"]) == 4
    phases = [r["phase"] for r in fsh["ranges"]]
    assert "Follicular Phase" in phases
    assert "Mid-cycle Peak" in phases
    assert "Luteal Phase" in phases
    assert "Postmenopausal" in phases
    # Range values preserved verbatim
    ranges = {r["range"] for r in fsh["ranges"]}
    assert "2.5-10.2" in ranges
    assert "23.0-116.3" in ranges
    # Simple panel with no phase should have empty string
    text_simple = """
Analyte
Value
HEMOGLOBIN
12.3
g/dL
Reference Range:
11.5-15.5
g/dL
"""
    out_simple = parse_labs(text_simple)
    assert out_simple[0]["ranges"][0]["phase"] == ""
    assert out_simple[0]["ranges"][0]["range"] == "11.5-15.5"


def test_parse_labs_multi_panel():
    # Two panels separated by repeated Analyte/Value header
    text = """
Analyte
Value
WHITE BLOOD CELL COUNT
5.0
Thousand/uL
Reference Range:
3.8-10.8
Thousand/uL
RED BLOOD CELL COUNT
3.77 L
Million/uL
Reference Range:
3.80-5.10
Million/uL

Analyte
Value
CHOLESTEROL, TOTAL
245 H
mg/dL
Reference Range:
0-200
mg/dL
TRIGLYCERIDES
180 H
mg/dL
Reference Range:
0-150
mg/dL
"""
    out = parse_labs(text)
    names = [t["name"] for t in out]
    assert len(out) == 4
    assert "WHITE BLOOD CELL COUNT" in names
    assert "RED BLOOD CELL COUNT" in names
    assert "CHOLESTEROL, TOTAL" in names
    assert "TRIGLYCERIDES" in names
    # Flags preserved across panels
    rbc = next(t for t in out if t["name"] == "RED BLOOD CELL COUNT")
    assert rbc["flag"] == "L"
    chol = next(t for t in out if "CHOLESTEROL" in t["name"])
    assert chol["flag"] == "H"


def test_parse_labs_fixture_quest_sample():
    fixture = Path(__file__).parent / "fixtures" / "quest_sample.txt"
    assert fixture.exists(), "fixtures/quest_sample.txt missing"
    text = fixture.read_text()
    out = parse_labs(text)
    # Fixture contains 6 labs across 3 panels
    assert len(out) == 6
    names = {t["name"] for t in out}
    assert "WHITE BLOOD CELL COUNT" in names
    assert "RED BLOOD CELL COUNT" in names
    assert "HEMOGLOBIN" in names
    assert "CHOLESTEROL, TOTAL" in names
    assert "TRIGLYCERIDES" in names
    assert "FSH" in names

    # Flags L/H present in fixture
    hb = next(t for t in out if t["name"] == "HEMOGLOBIN")
    assert hb["flag"] == "L"
    chol = next(t for t in out if "CHOLESTEROL" in t["name"])
    assert chol["flag"] == "H"
    trig = next(t for t in out if t["name"] == "TRIGLYCERIDES")
    assert trig["flag"] == "H"
    wbc = next(t for t in out if "WHITE BLOOD" in t["name"])
    assert wbc["flag"] == ""

    # Multi-phase FSH correctly parsed from fixture
    fsh = next(t for t in out if t["name"] == "FSH")
    assert len(fsh["ranges"]) == 4
    phase_map = {r["phase"]: r["range"] for r in fsh["ranges"]}
    assert phase_map["Follicular Phase"] == "2.5-10.2"
    assert phase_map["Mid-cycle Peak"] == "3.1-17.7"
    assert phase_map["Luteal Phase"] == "1.5-9.1"
    assert phase_map["Postmenopausal"] == "23.0-116.3"
    assert fsh["unit"] == "mIU/mL"
    assert fsh["value"] == 13.2

    # Units captured correctly
    wbc = next(t for t in out if "WHITE BLOOD" in t["name"])
    assert wbc["unit"] == "Thousand/uL"
    rbc = next(t for t in out if "RED BLOOD" in t["name"])
    assert rbc["unit"] == "Million/uL"

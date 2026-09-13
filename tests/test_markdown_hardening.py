"""HCH-2: harden markdown rendering — same-origin, fail-closed, CSP."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "static" / "index.html"
APP = ROOT / "static" / "app.js"


def _html():
    return HTML.read_text()


def _app():
    return APP.read_text()


def _csp_from_meta():
    html = _html()
    m = re.search(
        r'<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]+)"',
        html,
        re.I,
    )
    assert m, "CSP meta missing"
    return m.group(1)


def _directives(csp):
    out = {}
    for part in csp.split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, val = part.partition(" ")
        out[name.strip()] = val.strip()
    return out


def test_no_remote_executable_script():
    html = _html()
    # No remote script src in the page.
    for m in re.finditer(r'<script[^>]+src\s*=\s*["\']([^"\']+)["\']', html, re.I):
        src = m.group(1)
        assert not re.match(r"(?i)https?:", src), f"remote script: {src}"
        assert not src.startswith("//"), f"protocol-relative script: {src}"
        assert src.startswith("/static/"), f"non-local script: {src}"
    assert "cdn.jsdelivr" not in html.lower()
    assert "jsdelivr" not in html.lower()
    # App bundle itself must not pull remote code.
    if APP.exists():
        js = _app()
        assert "cdn.jsdelivr" not in js.lower()


def test_vendored_sanitizer_present():
    assert (ROOT / "static" / "purify.min.js").exists()
    assert (ROOT / "static" / "purify.min.js").stat().st_size > 1000
    assert (ROOT / "static" / "marked.min.js").exists()
    html = _html()
    assert "/static/purify.min.js" in html
    assert "/static/marked.min.js" in html
    assert "/static/app.js" in html


def test_md_fails_closed():
    js = _app() if APP.exists() else _html()
    # Missing sanitizer must throw to the esc fallback, not return raw HTML.
    assert 'throw new Error("no sanitizer")' in js or "no sanitizer" in js
    assert re.search(r"catch\s*\(e\)\s*\{\s*return esc\(text\);\s*\}", js), \
        "md() must return esc(text) on failure"
    assert "return raw;" not in js, "fail-open 'return raw' must be gone"


def test_csp_restrictive():
    csp = _csp_from_meta()
    d = _directives(csp)
    assert "'self'" in d.get("script-src", ""), f"script-src: {csp}"
    assert "http" not in d.get("script-src", ""), f"remote in script-src: {csp}"
    assert "'unsafe-inline'" not in d.get("script-src", ""), f"inline in script-src: {csp}"
    assert "'self'" in d.get("img-src", "") and "data:" in d.get("img-src", "")
    assert "http" not in d.get("img-src", ""), f"remote in img-src: {csp}"
    assert d.get("object-src", "") == "'none'", f"object-src: {csp}"
    assert d.get("base-uri", "") in ("'none'", "'self'"), f"base-uri: {csp}"


def test_sanitizer_blocks_remote_media_and_danger_tags():
    js = _app() if APP.exists() else _html()
    # Hook strips remote src/srcset/poster/background.
    assert "uponSanitizeAttribute" in js
    assert "keepAttr = false" in js
    # Dangerous sinks are forbidden even if markup slips through.
    for tag in ["object", "embed", "iframe", "form", "base"]:
        assert tag in js, f"FORBID_TAGS missing {tag}"


def test_csp_header_matches_meta():
    from fastapi.testclient import TestClient

    import server

    c = TestClient(server.app)
    r = c.get("/")
    assert r.status_code == 200
    hdr = r.headers.get("content-security-policy", "")
    assert "script-src 'self'" in hdr
    assert "object-src 'none'" in hdr
    assert "cdn.jsdelivr" not in r.text.lower()

#!/usr/bin/env python3
"""Fetch guideline excerpts listed in resources/manifest.json.

Public repo does NOT redistribute verbatim AAFP/ARUP text — this script
downloads it on the user's machine on first install. Keeps the repo
copyright-safe and the corpus fresh.

Usage:
  python scripts/fetch_guidelines.py              # fetch missing only
  python scripts/fetch_guidelines.py --force      # re-download all
  python scripts/fetch_guidelines.py --dry-run    # list what would be fetched

Each manifest entry expects {domain, file, url, short_name}. Fetched files
are saved to resources/<domain>/<file>. Existing files are left alone
unless --force is given.
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = Path(__file__).resolve().parent.parent
MANIFEST = BASE / "resources" / "manifest.json"

# Very small HTML -> text helper; keep deps zero. For better extraction,
# install `readability` or `trafilatura` locally and extend this.
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Expected keywords per file for validation (case-insensitive).
_EXPECTED_KEYWORDS: dict[str, list[str]] = {
    "hyperlipidemia_aafp.txt": ["cholesterol", "triglyceride", "hyperlipidemia", "LDL", "HDL"],
    "diabetes_a1c_statpearls.txt": ["HbA1c", "hemoglobin", "A1C", "glucose", "diabetes"],
    "kidney_evaluation_aafp.txt": ["creatinine", "eGFR", "kidney", "CKD", "albumin"],
    "liver_function_aafp.txt": ["ALT", "AST", "transaminase", "liver", "bilirubin"],
    "vitamin_d_statpearls.txt": ["vitamin D", "25-hydroxy", "cholecalciferol", "calcium"],
    "urinalysis_aafp.txt": ["urinalysis", "proteinuria", "hematuria", "urine"],
    "electrolytes_statpearls.txt": ["sodium", "potassium", "electrolyte", "hyponatremia", "chloride"],
    "vitamin_b12_statpearls.txt": ["vitamin B12", "cobalamin", "B12", "folate"],
    # fallbacks for older files (not strictly needed for validation)
    "hypoalbuminemia_statpearls.txt": ["albumin", "hypoalbuminemia"],
    "iron_deficiency_2025.txt": ["iron", "anemia"],
}

# Alternate user-agents to try if first is blocked.
_USER_AGENTS = [
    "health-chat fetcher (https://github.com/health-chat)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _extract_article_html(html: str) -> str:
    """Try to isolate the main article fragment before stripping tags."""
    # NCBI Bookshelf: <div class="... body-content ..." itemprop="text">
    m = re.search(r'<div[^>]*class="[^"]*body-content[^"]*"[^>]*>(.*)', html, flags=re.S | re.I)
    if m:
        frag = m.group(1)
        # Cut at footer if present to drop nav/footer boilerplate
        cut = re.search(r'<footer|<div[^>]*id="footer"|<div[^>]*class="[^"]*footer[^"]*"', frag, flags=re.I)
        if cut:
            frag = frag[: cut.start()]
        return frag
    # AAFP article tag
    m = re.search(r"<article[^>]*>(.*?)</article>", html, flags=re.S | re.I)
    if m:
        return m.group(1)
    # Generic article content div
    m = re.search(r'<div[^>]*class="[^"]*(?:article|cmp-article)[^"]*"[^>]*>(.*)', html, flags=re.S | re.I)
    if m:
        frag = m.group(1)
        cut = re.search(r'<footer|<div[^>]*class="[^"]*footer[^"]*"', frag, flags=re.I)
        if cut:
            frag = frag[: cut.start()]
        return frag
    return html


def html_to_text(html: str) -> str:
    # Isolate article first to avoid nav-heavy truncation.
    html = _extract_article_html(html)
    # Strip scripts/styles
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = _TAG_RE.sub(" ", html)
    # Decode entities
    text = html_lib.unescape(text)
    # Legacy fallbacks for any remaining entities
    text = text.replace("&nbsp;", " ")
    text = _WS_RE.sub(" ", text).strip()
    return text


def _is_block_page(text: str, expected: list[str] | None = None) -> bool:
    """Heuristic: page is a block/404 rather than article text."""
    low = text.lower()
    if len(text.strip()) < 300:
        return True
    # Common block markers
    block_phrases = ["requires javascript to function", "access denied", "403 forbidden", "404 not found", "page not found"]
    if any(p in low for p in block_phrases):
        # If it also contains expected keywords and is long, treat as valid (NCBI warning banner)
        if expected and any(k.lower() in low for k in expected) and len(text) > 2000:
            return False
        # NCBI warning alone without article content
        if "requires javascript" in low and expected and not any(k.lower() in low for k in expected):
            return True
        if "404" in low or "page not found" in low:
            return True
    return False


def _trim_to_core(text: str, url: str, short_name: str, expected: list[str] | None) -> str:
    """Trim `text` to ~3000-4000 chars of core content, keeping citation header."""
    header = f"Source: {url} ({short_name})\n\n"
    # If already short, just add header
    if len(text) <= 3800:
        return header + text
    # Try to find a good start offset near article markers
    markers = [
        "SORT: KEY RECOMMENDATIONS",
        "Continuing Education Activity",
        "Introduction",
        "Abstract",
        short_name,
    ]
    if expected:
        # Prefer the first expected keyword occurrence as anchor
        low = text.lower()
        best = None
        for kw in expected:
            idx = low.find(kw.lower())
            if idx != -1 and (best is None or idx < best):
                best = idx
        if best is not None and best > 500:
            # Start a bit before the keyword to keep context, but not before a marker
            start = max(0, best - 800)
            # Snap to nearest marker before keyword if found
            for m in markers:
                m_idx = text.rfind(m, 0, best)
                if m_idx != -1 and m_idx >= start - 500:
                    start = m_idx
                    break
            text = text[start:]
        else:
            # Fallback: find earliest marker in first half
            for m in markers:
                idx = text.find(m)
                if idx != -1 and idx < len(text) * 0.5:
                    text = text[idx:]
                    break
    else:
        for m in markers:
            idx = text.find(m)
            if idx != -1 and idx < len(text) * 0.5:
                text = text[idx:]
                break
    # Now slice to ~3500 chars, try to end at sentence boundary
    limit = 3600
    if len(text) > limit:
        cut = text.rfind(". ", 3000, limit)
        if cut != -1:
            text = text[: cut + 1]
        else:
            text = text[:limit]
    return header + text.strip()


def fetch_url(url: str, timeout: int = 30) -> str:
    last_exc: Exception | None = None
    for ua in _USER_AGENTS:
        try:
            req = Request(url, headers={"User-Agent": ua, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"})
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — intentionally fetching manifest URLs
                charset = resp.headers.get_content_charset() or "utf-8"
                data = resp.read().decode(charset, errors="replace")
                # If we got a JS-warning page but also have article, still return; validation happens later
                return data
        except (HTTPError, URLError, OSError) as exc:
            last_exc = exc
            # 404 is not UA-fixable, break early after first try
            if isinstance(exc, HTTPError) and exc.code in (404, 410):
                break
            continue
    if last_exc:
        raise last_exc
    raise URLError(f"failed to fetch {url}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch guideline excerpts per manifest")
    ap.add_argument("--force", action="store_true", help="re-download even if file exists and >200 chars")
    ap.add_argument("--dry-run", action="store_true", help="list actions without fetching")
    args = ap.parse_args()

    if not MANIFEST.exists():
        print(f"manifest not found: {MANIFEST}", file=sys.stderr)
        return 1
    data = json.loads(MANIFEST.read_text())
    entries = data.get("guidelines", [])
    if not entries:
        print("no guidelines in manifest", file=sys.stderr)
        return 1

    ok = 0
    skipped = 0
    failed = 0
    for e in entries:
        domain = e["domain"]
        filename = e["file"]
        url = e["url"]
        dest = BASE / "resources" / domain / filename
        if dest.exists() and dest.read_text(errors="replace").strip().__len__() > 200 and not args.force:
            skipped += 1
            if args.dry_run:
                print(f"skip  {domain}/{filename} (exists)")
            continue
        if args.dry_run:
            print(f"fetch {domain}/{filename} <- {url}")
            continue
        try:
            print(f"fetch {domain}/{filename} ...", end=" ", flush=True)
            raw = fetch_url(url)
            # If HTML, extract text; if already plain, keep as-is
            is_html = "<html" in raw.lower() or "<!doctype" in raw.lower() or "<head" in raw.lower()
            text = html_to_text(raw) if is_html else raw
            expected = _EXPECTED_KEYWORDS.get(filename)
            # Validate not a block/404 page
            if _is_block_page(text, expected):
                raise ValueError(f"fetched content looks like block/404 page (len {len(text)}, missing keywords {expected})")
            # Trim to ~3000-4000 chars core + citation header
            short = e.get("short_name", filename)
            text = _trim_to_core(text, url, short, expected)
            # Final validation: >500 chars and contains at least one expected keyword if known
            if len(text) < 500:
                raise ValueError(f"content too short after trim: {len(text)} chars")
            if expected and not any(k.lower() in text.lower() for k in expected):
                raise ValueError(f"missing expected keywords {expected} in fetched text")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text)
            print(f"ok ({len(text)} chars -> {dest})")
            ok += 1
        except (HTTPError, URLError, OSError, ValueError) as exc:
            print(f"FAIL: {exc}")
            failed += 1

    print(f"\ndone: {ok} fetched, {skipped} skipped, {failed} failed")
    if failed and not args.dry_run:
        print("Hint: some sites block bots — manually save the excerpt via browser and place at the dest path.", file=sys.stderr)
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

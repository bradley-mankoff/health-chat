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


def html_to_text(html: str) -> str:
    # Strip scripts/styles
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = _TAG_RE.sub(" ", html)
    # Decode a few entities without full parser
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    text = _WS_RE.sub(" ", text).strip()
    return text


def fetch_url(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": "health-chat fetcher (https://github.com/health-chat)"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — intentionally fetching manifest URLs
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


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
            text = html_to_text(raw) if "<html" in raw.lower() or "<!doctype" in raw.lower() else raw
            # Trim to ~3000 chars focused excerpt if too long; keep head for now
            # (curator should manually trim to <300 words for fair-use before commit)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text[:12000])
            print(f"ok ({len(text)} chars -> {dest})")
            ok += 1
        except (HTTPError, URLError, OSError) as exc:
            print(f"FAIL: {exc}")
            failed += 1

    print(f"\ndone: {ok} fetched, {skipped} skipped, {failed} failed")
    if failed and not args.dry_run:
        print("Hint: some sites block bots — manually save the excerpt via browser and place at the dest path.", file=sys.stderr)
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

# Guidelines Corpus

**Verbatim guideline text is NOT shipped in the public repo** (copyright). Instead:

1. `manifest.json` lists canonical URLs + short citation names.
2. On first install, run:

```bash
.venv/bin/python scripts/fetch_guidelines.py
```

That downloads each URL to `resources/<domain>/<file>` on your machine.

Existing `resources/<domain>/*.txt` files in your local checkout were fetched this way — they are `.gitignore`'d in the public repo (only `manifest.json` is committed). If you add a new lab domain, add an entry to `manifest.json` (see `planned_additions`) then fetch.

Keep excerpts <300 words where possible and always keep the source URL in `GUIDELINE_SOURCES` in `server.py`.

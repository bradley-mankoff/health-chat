# Dependencies — hash-locked installs

`pyproject.toml` is the human-edited source of truth (loose bounds). The committed
locks are derived artifacts — generated, never hand-edited:

- `requirements.txt` — production lock: full transitive closure of
  `[project].dependencies`, every pin with `--hash=sha256` lines. No test-only deps.
- `requirements-dev.txt` — dev lock: superset of production plus the `dev` extra.
  Each install mode reads exactly one file.

Both installers consume the lock verbatim (`pip install --require-hashes -r <lock>`,
then `pip install -e . --no-deps`), so `--require-hashes` hard-fails on anything
unpinned instead of silently floating.

## Refreshing

```bash
bash scripts/refresh_locks.sh
```

(Windows/PowerShell: run the same two `uv pip compile …` lines from the script;
uv has native Windows builds and output is byte-identical.) The
`--python-version 3.10` flag anchors resolution to the repo's Python floor —
without it, version-sensitive pins resolve for the local interpreter and can
silently break 3.10. Checklist after refreshing: scan, then gate, then commit
both files.

## Advisory scan (contract for HCH-24 automation)

```bash
uvx pip-audit -r requirements.txt --no-deps
uvx pip-audit -r requirements-dev.txt --no-deps
```

`--no-deps` because the lock is already the complete transitive closure.
Exit 0 / `No known vulnerabilities found` = clean.

## Advisory exceptions

| GHSA/PyPA id | package | affected pin | reason | expires | owner |
|---|---|---|---|---|---|
| _(none)_ | | | | | No open exceptions. |

Policy: a non-clean scan is fixed by refreshing to a fixed release first; only
when no compatible fix exists may a row be added, and the scan/CI command gains
one `--ignore-vuln <ID>` per row (mirrored here for HCH-24). No entry without
expiry date and owner.

## Known residual

`pip install -e . --no-deps` still builds via isolated-build `[build-system]`
(`setuptools`, `wheel` float). Out of scope for runtime deps; noted, not solved.

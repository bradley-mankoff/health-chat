# Security & Privacy Model

## What "private" means in v1

- **Fully local by default.** Your PDFs stay on disk in `./data` (or `DATA_DIR`). The server only talks to the local LLM at `LLM_URL` (default `http://127.0.0.1:8080`). No documents, chat history, or lab values are sent to any cloud API.
- **No outbound network in v1.** There is no web search, no analytics, no telemetry. The only outbound HTTP the server makes is to the local LLM.
- **Guideline fetcher is opt-in.** `scripts/fetch_guidelines.py` downloads public guideline excerpts from their publishers. It does not send your health data anywhere.

## What is NOT protected

- **Loopback only, but not encrypted.** The app binds `127.0.0.1:8787` by default (override with `HOST`). It does not use TLS. Do not expose the port to a network or the internet — anyone with network access and the passcode could read your records.
- **Passcode is not HIPAA auth.** The `Bearer` passcode in `.passcode` prevents casual local access, but it is a shared secret stored in plaintext. Treat it like a local password, not a compliance mechanism.
- **No encryption at rest.** PDFs and the local LLM's context are stored as plain files. Full-disk encryption is your responsibility.
- **Browser storage.** Chat history lives in your browser session. Clearing site data clears it.
- **LLM prompt logging contains PHI.** When `LLM_URL` points to a local `llama-server`, prompts (including lab values, names, and chat history) are sent to that process. If that server logs prompts or you proxy `LLM_URL` to a non-local endpoint, logs may contain PHI — keep `LLM_URL` on loopback and disable remote logging.

## Threat model — honest limitations (employer-visible)

- **XSS via LLM markdown (mitigated by sanitization).** Model output is rendered as markdown via `marked`. Raw HTML from model/retrieved text is escaped before rendering and markdown is sanitized (no inline `<script>` execution). Treat sanitization as a trust boundary; if you change the renderer, re-audit.
- **Path disclosure via `/api/health` (only basename).** Health endpoint returns chunk/file counts for diagnostics; if file paths were exposed, absolute `DATA_DIR` could leak. The response exposes only basenames (or is designed to expose only basenames) and requires `Authorization: Bearer <passcode>` — do not add absolute paths to unauthenticated responses.
- **LLM prompt logging contains PHI.** See "What is NOT protected" above — prompts carry record excerpts. Ensure local LLM logs are not shipped to third parties and consider disabling request logging on `llama-server`.
- **Supply-chain SRI for `marked.min.js`.** The frontend loads `/static/marked.min.js` (vendored `marked v12.0.2`). Verify its integrity with an SRI hash when served from a CDN or after updating the vendored file (e.g. `<script integrity="sha384-…" crossorigin="anonymous" src="…">`) and pin the version in `package.json`/lockfile to prevent silent upgrades.
- **JOBS eviction is FIFO (bounded memory).** In-memory chat jobs are capped at `_MAX_JOBS=30`; the oldest job is evicted first (`FIFO`) via `_prune_jobs()` when the cap is exceeded. Eviction is intentional to bound memory — a pending job that is evicted returns `404 job expired` and the client must retry.

## Recommendations

- Keep `HOST=127.0.0.1` (default). If you set `HOST=0.0.0.0`, put the app behind a VPN or authenticated reverse proxy with TLS.
- Do not upload records you are not comfortable having on that machine.
- If you enable any future `--online` search flag (v2), search queries will be sanitized to remove identifiers — see backlog ticket.

## Reporting

If you find a security issue, please open a private security advisory on GitHub rather than a public issue.

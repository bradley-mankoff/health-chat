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

## Recommendations

- Keep `HOST=127.0.0.1` (default). If you set `HOST=0.0.0.0`, put the app behind a VPN or authenticated reverse proxy with TLS.
- Do not upload records you are not comfortable having on that machine.
- If you enable any future `--online` search flag (v2), search queries will be sanitized to remove identifiers — see backlog ticket.

## Reporting

If you find a security issue, please open a private security advisory on GitHub rather than a public issue.

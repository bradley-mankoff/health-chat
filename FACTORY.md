# Factory (health-chat)

The Mode B factory wraps this repo; the rules live there, not here.
Manual: `../omp-modes/docs/human.md`. Behavior defaults are shared — this
repo carries identity plus deliberate deviations only (see `factory.json`).

Repo identity:

- Piyaz project **HCH** ("Health Chat", Bradley's Team) — the task graph.
- Base branch `main`. Git/GitHub stays the code layer.
- Gate: `pytest -q`.
- Deviations: 3 concurrent workflows (shared default: 1).

Your job is ideas and gates. Taste waits for you; mechanical work with full
evidence and green checks finishes on its own and flips its ticket done.

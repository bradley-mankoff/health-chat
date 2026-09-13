---
description: Forced-fuse judge for three isolated implementations. Writes $ARTIFACTS_DIR/fused/ then emits JSON.
argument-hint: the original user request
---

# Fusion judge — three implementations, forced fuse

Three panels implemented the request. Synthesize them. Do not merely pick one.

## Request

$ARGUMENTS

## Candidates

- Panel a — `$ARTIFACTS_DIR/reports/a.md` — `$ARTIFACTS_DIR/panels/a/`
- Panel b — `$ARTIFACTS_DIR/reports/b.md` — `$ARTIFACTS_DIR/panels/b/`
- Panel c — `$ARTIFACTS_DIR/reports/c.md` — `$ARTIFACTS_DIR/panels/c/`

Read the reports, then the files. Fuse the strongest ideas into your own tree.

1. `mkdir -p $ARTIFACTS_DIR/fused`
2. Write a complete implementation there. Not a diff, not a symlink.
3. Then emit exactly:

```json
{"verdict": "...", "mode": "fuse", "chosen": "a"}
```

`chosen` is `"a"`, `"b"`, or `"c"` — fallback only. Emitting JSON without the fused tree is a failure.

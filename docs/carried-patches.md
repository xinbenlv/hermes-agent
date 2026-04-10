# Carried Patches Policy

This repo uses a carried patch queue on top of upstream `origin/main`.

## CPQ layers

- `cpq-cornerstone-*` — local foundation and workflow carries
- `patch-fix-test-pr*` — upstream-bound test fixes
- `patch-fix-func-pr*` — upstream-bound functional fixes
- `patch-feat-pr*` — upstream-bound feature carries
- `cpq-capstone-*` — top-of-stack branding and metadata carries

## Sources of truth

- Policy and workflow overview: `docs/carried-patches.md`
- Live patch metadata ledger: `docs/carried-patch-ledger.yaml`
- Operational workflow: `skills/github/hermes-carried-patch-workflow/SKILL.md`
- Full patch rationale: the Markdown commit message body of each carried patch commit

## Queue invariants

- `cpq-capstone-2` is the canonical metadata snapshot for the current queue.
- `cpq-head` must point to `cpq-capstone-2`.
- Any mutation anywhere in `cpq-base..cpq-head` invalidates the old `cpq-capstone-2`.
- After changing `cpq-base`, adding/removing/reordering/rewording/amending commits, or changing patch IDs / PR mappings / ledger contents, rebuild `cpq-capstone-2` last.

## Ledger rules

- `docs/carried-patch-ledger.yaml` records the current active patch set only.
- Keep the ledger minimal: patch id, current commit, upstream PR URL if applicable.
- `cpq-capstone-2` is a special case: its ledger entry uses `current_commit: cpq-head` because a self-hash cannot be embedded inside the commit that defines it without becoming stale immediately.
- Regenerate the ledger only after the rest of the queue is finalized.

## Commit message rules

Every carried patch commit must have:

- a stable patch-id subject line
- a Markdown body shaped like a PR description
- upstream PR URL and status when applicable
- why-carried and drop-condition sections

Recommended sections:

- `## Why carried`
- `## Upstream`
- `## Summary`
- `## Drop condition`
- `## Files`

## Upstream backlink rule

Every upstream-bound carried patch PR body must include a literal backlink line:

```md
Carried patch: patch-feat-pr6456
```

## Push gate

Do not push a mutated queue until all are true:

- carried commit bodies are complete
- `docs/carried-patch-ledger.yaml` matches the current queue
- `cpq-capstone-2` was rebuilt last
- `cpq-head` points to the rebuilt `cpq-capstone-2`

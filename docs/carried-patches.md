# Carried Patches Policy

This repo uses a carried patch queue on top of upstream `origin/main`.

## CPQ layers

- `cpq-cornerstone-*` — local foundation and workflow carries
- `patch-fix-test-pr*` — upstream-bound test fixes
- `patch-fix-func-pr*` — upstream-bound functional fixes
- `patch-feat-pr*` — upstream-bound feature carries
- `cpq-capstone-*` — top-of-stack branding and metadata carries

Required queue order inside `cpq-body`:

1. `patch-fix-test-pr*`
2. `patch-fix-func-pr*`
3. `patch-feat-pr*`

## Sources of truth

- Policy and workflow overview: `docs/carried-patches.md`
- Live patch metadata ledger: `docs/carried-patch-ledger.yaml`
- Operational workflow: `skills/github/hermes-carried-patch-workflow/SKILL.md`
- Full patch rationale: the Markdown commit message body of each carried patch commit

## Queue invariants

- `cpq-cornerstone-0`, `cpq-cornerstone-1`, `cpq-capstone-1`, and `cpq-capstone-2` are required structural patches in the active queue, each exactly once.
- `cpq-cornerstone-0` must appear before `cpq-cornerstone-1`.
- `cpq-capstone-1` must appear before `cpq-capstone-2`.
- patch buckets are optional, but if present they must stay ordered as `patch-fix-test-pr*` -> `patch-fix-func-pr*` -> `patch-feat-pr*`.
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
- machine-readable metadata declared in body frontmatter when possible: `upstream:` (`null` for local-only carries) and `files:`
- `## Summary` and `## Drop condition` sections for the free-text part

Recommended sections:

- `## Why carried`

Preferred shape:

```md
patch-feat-pr9999: short title

---
upstream: https://github.com/NousResearch/hermes-agent/pull/9999
files:
  - path/to/file.py
---

## Summary
- What changed.

## Drop condition
- When to remove the carry.
```

Legacy compatibility note:

- Older carried commits may still use a Markdown `## Upstream` section with a single `PR:` line.
- Older carried commits may still use a Markdown `## Files` section.
- `Status:` is no longer required.

## Upstream backlink rule

Every upstream-bound carried patch PR body must include a literal backlink line:

```md
Carried patch: patch-feat-pr6456
```

## Queue maintenance rule

When updating to a newer upstream `origin/main`, treat the operation as: move to the new upstream baseline, reevaluate every carried patch from the prior queue, replay only the still-needed carries in bucket order, then rebuild `cpq-capstone-2` last. Do not mechanically replay the old `cpq-capstone-2`; it must be recomposed because the active carried commit hashes changed.

Refreshing `refs/cpq/base` and `refs/cpq/head` is part of that final capstone rebuild/alignment flow, not a conceptually separate maintenance phase.

## Push gate

Do not push a mutated queue until all are true:

- carried commit bodies are complete
- `docs/carried-patch-ledger.yaml` matches the current queue
- `cpq-capstone-2` was rebuilt last
- `cpq-head` points to the rebuilt `cpq-capstone-2`

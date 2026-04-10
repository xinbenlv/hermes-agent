---
name: hermes-carried-patch-workflow
description: Maintain the downstream CPQ queue in xinbenlv/hermes-agent, keep metadata in a live YAML ledger, and force cpq-capstone-2 rebuilds after any queue mutation.
version: 1.4.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [github, carried-patches, downstream, fork, rebase, worktree, cpq]
    related_skills: [github-pr-workflow, github-code-review, hermes-agent]
---

# Hermes carried patch workflow

Use this skill when working in `xinbenlv/hermes-agent` as a downstream fork of `NousResearch/hermes-agent`.

## Core model

- `origin/main` = clean upstream source of truth.
- local `main` = `origin/main` + the carried patch queue.
- `fork/main` = remote mirror of local `main`, not a pristine upstream mirror.
- `cpq-capstone-2` is the canonical metadata snapshot for the current queue.
- `cpq-head` must point to `cpq-capstone-2`.
- Any mutation in `cpq-base..cpq-head` invalidates the old `cpq-capstone-2`.

## Patch naming rules

Use human-meaningful patch IDs in carried commit subjects.

- `cpq-cornerstone-<N>` for downstream foundation carries.
- `patch-fix-test-pr<PR_NUMBER>` for upstream-bound test fixes.
- `patch-fix-func-pr<PR_NUMBER>` for upstream-bound functional bugfixes.
- `patch-feat-pr<PR_NUMBER>` for upstream-bound feature carries.
- `cpq-capstone-<N>` for top-of-stack downstream branding and metadata carries.

## Sources of truth

- `docs/carried-patches.md` = policy and invariants only.
- `docs/carried-patch-ledger.yaml` = live patch metadata ledger.
- carried commit message body = full patch rationale, written in Markdown like a PR description.

Do not dump detailed per-patch prose into `docs/carried-patches.md`. That is exactly how the queue turns back into sludge.

## Required commit body format

Every carried patch commit must have a Markdown body with these sections:

```md
## Why carried
- ...

## Upstream
- PR: https://github.com/.../pull/1234
- Status: open

## Summary
- ...

## Drop condition
- ...

## Files
- `path/to/file`
```

For local-only carries, use:

```md
## Upstream
- PR: null
- Status: local-only
```

## Ledger format

`docs/carried-patch-ledger.yaml` must stay minimal:

```yaml
patches:
  - id: patch-feat-pr6456
    current_commit: 9963501c
    upstream_pr: https://github.com/NousResearch/hermes-agent/pull/6456
```

Special case:
- `cpq-capstone-2` uses `current_commit: cpq-head` in the ledger.
- Reason: embedding the commit's own final hash inside itself is a stupid fixed-point problem.

## Mandatory rebuild triggers

You MUST rebuild `cpq-capstone-2` after any of these:

- changing `cpq-base`
- adding a carried commit
- dropping a carried commit
- reordering carried commits
- amending, rebasing, squashing, or rewording any carried commit
- changing a patch ID
- changing upstream PR mapping / URL
- changing ledger contents
- changing any file in the queue in a way that alters any carried commit hash

Short version: if anything in `cpq-base..cpq-head` changed, rebuild `cpq-capstone-2` last.

## Hooks

This repo uses CPQ guard hooks under `.githooks/`.

Enable them locally:

```bash
git config core.hooksPath .githooks
```

Expected hooks:
- `commit-msg` validates Markdown commit bodies for carried patches.
- `pre-commit` warns when staged changes mutate CPQ state and therefore require a final capstone rebuild.
- `pre-push` blocks pushes if the ledger is stale, `cpq-capstone-2` is not last, or `cpq-head` is not aligned.
- `scripts/cpq_checks.py rebuild-ledger` regenerates the YAML ledger from the current carried queue.
- `scripts/cpq_checks.py rebuild-capstone` regenerates the ledger, creates or amends `cpq-capstone-2`, and refreshes `refs/cpq/base` + `refs/cpq/head`.

## Daily workflow

### 1. Inspect state first

```bash
git fetch origin --prune
git fetch fork --prune
git status --short --branch
git log --reverse --oneline origin/main..main
```

### 2. Do upstreamable work in a clean worktree

```bash
mkdir -p .worktrees
git worktree add .worktrees/feat-some-change origin/main -b feat/some-change
```

### 3. Keep carried metadata explicit

Whenever you create or mutate a carried patch:
- update the commit body
- update the upstream PR body backlink if applicable
- run `python3 scripts/cpq_checks.py rebuild-ledger` if you only need to refresh the ledger during work
- run `python3 scripts/cpq_checks.py rebuild-capstone` as the final step after any queue mutation

### 4. Maintain CPQ refs after rebuild

After the queue is finalized, update local refs:

```bash
git update-ref refs/cpq/base $(git merge-base origin/main HEAD)
git update-ref refs/cpq/head HEAD
```

### 5. Push only after verification

```bash
python3 scripts/cpq_checks.py rebuild-capstone
python3 scripts/cpq_checks.py verify
git push --force-with-lease fork main:main
```

## Done criteria

You are done only when all are true:
- local `main` is based on current `origin/main`
- every carried patch commit has the required Markdown body
- `docs/carried-patch-ledger.yaml` matches the current queue
- `cpq-capstone-2` is the final carried commit
- `cpq-head` points to `cpq-capstone-2`
- each upstream-bound patch links to its upstream PR
- each upstream PR body links back with `Carried patch: <patch-id>`
- `fork/main` mirrors local `main`

## Anti-patterns

- storing the full patch encyclopedia in `docs/carried-patches.md`
- mutating the queue and forgetting to rebuild `cpq-capstone-2`
- pushing while `cpq-head` still points at an old capstone snapshot
- using anonymous commit bodies or empty commit bodies for carried patches
- treating the ledger as prose instead of a minimal live index

## Rebuild commands

Use these instead of hand-editing the ledger like an animal.

### `python3 scripts/cpq_checks.py rebuild-ledger`
- Recomputes `docs/carried-patch-ledger.yaml` from the current carried queue.
- Use while preparing a queue rewrite, but it does not update `cpq-head`.

### `python3 scripts/cpq_checks.py rebuild-capstone`
- Recomputes the ledger.
- If `HEAD` is already `cpq-capstone-2`, amends that commit in place.
- Otherwise creates a fresh `cpq-capstone-2` commit on top of the queue.
- Updates `refs/cpq/base` and `refs/cpq/head` to the rebuilt queue state.

This command is the required final step after any mutation in `cpq-base..cpq-head`.

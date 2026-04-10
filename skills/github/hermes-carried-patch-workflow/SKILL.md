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

## Queue insertion rule

Inside `cpq-body`, ordering is mandatory:

1. `patch-fix-test-pr*`
2. `patch-fix-func-pr*`
3. `patch-feat-pr*`

When adding a new carried patch, insert it into its bucket.
Do not append it at the top of `cpq-body` just because that is convenient.
Always rebuild `cpq-capstone-2` last.

## Required commit body format

Prefer machine-readable frontmatter for metadata and keep Markdown for free text:

```md
patch-feat-pr1234: short title

---
upstream: https://github.com/NousResearch/hermes-agent/pull/1234
files:
  - path/to/file.py
  - other/path.txt
---

## Summary
- ...

## Drop condition
- ...
```

`## Why carried` is recommended, not required.

For local-only carries, use:

```md
---
upstream: null
files:
  - path/to/file.py
---
```

Legacy carries may still use Markdown `## Upstream` / `## Files`, but when rewriting or touching old carries, migrate those fields into frontmatter instead of preserving the old shape.

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

### 2. Start new own fix/feat work from `cpq-base`, in a clean worktree

For new downstream patch candidates, branch from the current `cpq-base`, not from `cpq-head`/`main`.
That keeps the patch injectible into the queue later instead of accidentally baking later carried layers into it.

```bash
BASE=$(git merge-base origin/main HEAD)
mkdir -p .worktrees
git worktree add .worktrees/feat-some-change "$BASE" -b feat/some-change
```

If you open an upstream PR from that branch, still target upstream `main`; the branch base is about keeping the patch clean, not about changing the PR base.

### 3. Update to upstream main, reevaluate the queue, then rebuild CPQ as one flow

Treat upstream update + CPQ replay as a single operation, not two fake-independent chores.

Required flow:
- move the working branch to the new upstream `origin/main` baseline
- inspect the previous carried queue from old `cpq-base..cpq-head`
- reevaluate each carried patch against the new upstream baseline
- drop any carry that is already upstreamed, obsolete, or no longer justified
- replay only the still-needed carries in mandatory bucket order
- do **not** preserve old `cpq-capstone-2`; recompose it last from the final replayed queue because carried commit hashes changed
- refresh `refs/cpq/base` and `refs/cpq/head` as part of that final rebuild, not as a mentally separate maintenance step

Practical consequence: `cpq-capstone-2` is not a normal patch to replay. It is a regenerated metadata snapshot derived from the new active queue.

### 4. Push only after verification

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
- dropping `cpq-cornerstone-*` or `cpq-capstone-*` from the active queue during maintenance; those commits are structural, not decorative
- if only `cpq-capstone-1` is missing/bad, needlessly resetting deeper carried history instead of rewriting from the parent of `cpq-capstone-1` upward and then rebuilding `cpq-capstone-2`
- using anonymous commit bodies or empty commit bodies for carried patches
- treating the ledger as prose instead of a minimal live index
- starting a new own `fix/*` or `feat/*` branch from `cpq-head` when it should have started from `cpq-base`
- using naive `self.console.print(...)` for TUI-facing CLI output and then acting surprised when Rich highlight/markup sprays broken ANSI junk; use `_cprint(...)`, `ChatConsole().print(...)`, or explicitly disable `highlight`/`markup`
- forgetting that GitHub PR base semantics are branch-only. Even if `cpq-base` is a real commit on `upstream/main` with the same hash, you still cannot base a PR on that commit directly, or on a tag/revision like `main~10`; if you need a historical anchor for CI/review, create a branch at that commit first.
- trusting older global/shared CPQ instructions over repo-local CPQ sources of truth. For this repo, patch naming/backlinks must come from `skills/github/hermes-carried-patch-workflow/SKILL.md`, `docs/carried-patches.md`, and `docs/carried-patch-ledger.yaml`; do not resurrect dead `patch-upstream-pr-*` naming from stale guidance.
- debugging a red `cpq-head` by hand-waving about flakiness. First isolate the currently failing test subset at `cpq-head`, then bisect only across carried commits to find the first bad patch, then fix, then rerun a broader targeted test set before attempting an expensive full suite. Subset-first bisect beats guessing.
- keeping a carried patch bound to the wrong upstream identity. This is broader than "our old PR died": sometimes our PR gets replaced, sometimes we never opened one and want to cherry-pick someone else's merge-pending PR. In all such cases, if CPQ chooses to follow an external merge-pending PR, treat that external PR as the real upstream successor/source of truth: map the carried patch to that active PR, realign the carried implementation toward that PR when needed, and update ledger/body/backlinks/drop-condition together. This is the CPQ way to cherry-pick external merge-pending PRs without leaving ghost PR numbers or fake provenance in the queue.
- when a carried patch is intentionally following an external merge-pending PR, the commit body can stay lightweight: say clearly that this carry tracks that external PR and rely on the external PR for the detailed implementation narrative. Do not duplicate the full design essay locally unless we have real downstream-only deltas. But always keep the upstream PR link in the commit body and the `Carried patch: <patch-id>` backlink in the PR body.
- following an external PR does NOT give you permission to break CPQ ordering. Even externally sourced carries still belong to the normal CPQ layers and order: test fixes in `patch-fix-test-pr*`, then functional fixes in `patch-fix-func-pr*`, then features in `patch-feat-pr*`, with capstones rebuilt last. Provenance may be external; queue discipline is still ours.
- `cpq-capstone-2` must describe the full active carried queue, not just "our own PRs". Its ledger snapshot and metadata need to cover every carried patch currently in the stack: local-only carries, carries mapped to our upstream PRs, and carries intentionally following external merge-pending PRs. Capstone is the truth snapshot of the whole queue or it is useless.

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

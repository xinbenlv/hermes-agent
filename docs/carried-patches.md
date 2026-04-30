# Carried Patches Policy

This fork uses a Carried Patch Queue (CPQ) on top of upstream.

**Operational guidance, conventions, scripts, and templates all live in the
canonical repo-cpq skill:**

  https://github.com/xinbenlv/opc/tree/main/skills/repo-cpq

When working with the carried queue — adding, dropping, reordering,
syncing to a new upstream baseline, debugging a red `cpq-head`, or
auditing state — follow that skill, not stale per-repo guidance.

## Local invariants

- `upstream` remote = pristine upstream; `origin` = our fork.
- Linear queue: cornerstones (asc) → fix-test → fix-func → feat → capstones (desc, capstone-0 last).
- `cpq-capstone-0` is the canonical metadata snapshot for the current queue.
- `cpq-head` must point to `cpq-capstone-0`.
- `refs/cpq/{base,head}` must be aligned (managed by `scripts/cpq-checks.mjs rebuild-capstone`).
- No merge commits in `cpq-base..cpq-head`.

## Verifier

`node scripts/cpq-checks.mjs <subcommand>`:

- `check-remotes`     — verify the upstream/origin remote convention
- `rebuild-ledger`    — regenerate `docs/carried-patch-ledger.yaml`
- `rebuild-capstone`  — regenerate ledger + amend/create cpq-capstone-0 + refs
- `verify`            — full validity check (used by pre-push)
- `pre-commit`        — warn on staged CPQ governance changes
- `commit-msg <file>` — validate a single commit message

## Hooks

`core.hooksPath` is set to `git-hooks`. The hooks delegate to the verifier.

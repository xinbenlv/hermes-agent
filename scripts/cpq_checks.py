#!/usr/bin/env python3
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "carried-patch-ledger.yaml"
CPQ_FILES = {
    "AGENTS.md",
    "docs/carried-patches.md",
    "docs/carried-patch-ledger.yaml",
    "skills/github/hermes-carried-patch-workflow/SKILL.md",
    "scripts/cpq_checks.py",
    ".githooks/pre-commit",
    ".githooks/commit-msg",
    ".githooks/pre-push",
}
REQUIRED_HEADERS = [
    "## Why carried",
    "## Upstream",
    "## Summary",
    "## Drop condition",
    "## Files",
]


CAPSTONE_SUBJECT = "cpq-capstone-2: rebuild live CPQ metadata ledger"
CAPSTONE_BODY = """## Why carried
- The queue needs a final metadata snapshot that reflects the actual carried commits after every mutation.
- Without a rebuilt capstone, `cpq-head` lies and the ledger rots immediately.

## Upstream
- PR: null
- Status: local-only

## Summary
- Rebuilds `docs/carried-patch-ledger.yaml` from the finalized carried queue.
- Reasserts that `cpq-head` points to the rebuilt `cpq-capstone-2` metadata snapshot.

## Drop condition
- Drop only if this repo abandons the current CPQ ledger model entirely.

## Files
- `docs/carried-patch-ledger.yaml`
"""


def git_quiet(*args: str):
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def current_head_subject():
    return git("show", "-s", "--format=%s", "HEAD")


def update_cpq_refs():
    base = git("merge-base", "origin/main", "HEAD")
    head = git("rev-parse", "HEAD")
    git("update-ref", "refs/cpq/base", base)
    git("update-ref", "refs/cpq/head", head)


def build_capstone_message():
    return CAPSTONE_SUBJECT + "\n\n" + CAPSTONE_BODY


def append_capstone_entry(path: Path):
    text = path.read_text().rstrip() + """

  - id: cpq-capstone-2
    current_commit: cpq-head
    upstream_pr: null
"""
    path.write_text(text)


def rebuild_capstone():
    write_ledger(LEDGER)
    append_capstone_entry(LEDGER)
    git("add", str(LEDGER.relative_to(ROOT)))
    message = build_capstone_message()
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write(message)
        msg_path = f.name
    try:
        if current_head_subject().startswith("cpq-capstone-2:"):
            git("commit", "--amend", "-F", msg_path)
        else:
            git("commit", "-F", msg_path)
    finally:
        Path(msg_path).unlink(missing_ok=True)
    update_cpq_refs()


def git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def carried_commits():
    base = git("merge-base", "origin/main", "HEAD")
    raw = git("log", "--reverse", "--format=%H%x1f%s", f"{base}..HEAD")
    commits = []
    if raw:
        for line in raw.splitlines():
            sha, subject = line.split("\x1f", 1)
            patch_id = subject.split(":", 1)[0].strip()
            commits.append({"sha": sha, "short": sha[:8], "subject": subject, "id": patch_id})
    return base, commits


def upstream_pr_url(patch_id: str):
    m = re.match(r"patch-(?:fix-test|fix-func|feat)-pr(\d+)$", patch_id)
    if not m:
        return None
    return f"https://github.com/NousResearch/hermes-agent/pull/{m.group(1)}"


def parse_ledger(path: Path):
    entries = []
    if not path.exists():
        raise SystemExit(f"missing ledger: {path}")
    current = None
    for raw_line in path.read_text().splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped == "patches:":
            continue
        if stripped.startswith("- id:"):
            if current:
                entries.append(current)
            current = {"id": stripped.split(":", 1)[1].strip()}
        elif current and stripped.startswith("current_commit:"):
            value = stripped.split(":", 1)[1].strip()
            current["current_commit"] = None if value == "null" else value
        elif current and stripped.startswith("upstream_pr:"):
            value = stripped.split(":", 1)[1].strip()
            current["upstream_pr"] = None if value == "null" else value
    if current:
        entries.append(current)
    return entries


def write_ledger(path: Path):
    _, commits = carried_commits()
    lines = ["patches:"]
    for c in commits:
        url = upstream_pr_url(c["id"])
        current = "cpq-head" if c["id"] == "cpq-capstone-2" else c["short"]
        lines.extend([
            f"  - id: {c['id']}",
            f"    current_commit: {current}",
            f"    upstream_pr: {url if url else 'null'}",
            "",
        ])
    path.write_text("\n".join(lines).rstrip() + "\n")


def verify():
    base, commits = carried_commits()
    if not commits:
        raise SystemExit("no carried commits found")
    if commits[-1]["id"] != "cpq-capstone-2":
        raise SystemExit("last carried commit is not cpq-capstone-2; rebuild cpq-capstone-2 last")
    entries = parse_ledger(LEDGER)
    expected_ids = [c["id"] for c in commits]
    actual_ids = [e.get("id") for e in entries]
    if expected_ids != actual_ids:
        raise SystemExit(f"ledger patch IDs do not match queue\nexpected: {expected_ids}\nactual:   {actual_ids}")
    for c, e in zip(commits, entries):
        expected_url = upstream_pr_url(c["id"])
        if c["id"] == "cpq-capstone-2":
            if e.get("current_commit") != "cpq-head":
                raise SystemExit("cpq-capstone-2 ledger entry must use current_commit: cpq-head")
        else:
            if e.get("current_commit") != c["short"]:
                raise SystemExit(f"ledger hash mismatch for {c['id']}: expected {c['short']} got {e.get('current_commit')}")
        if e.get("upstream_pr") != expected_url:
            raise SystemExit(f"ledger upstream PR mismatch for {c['id']}: expected {expected_url} got {e.get('upstream_pr')}")
    head_subject = git("show", "-s", "--format=%s", "HEAD")
    if not head_subject.startswith("cpq-capstone-2:"):
        raise SystemExit("HEAD is not cpq-capstone-2")
    cpq_head = git("rev-parse", "--verify", "refs/cpq/head", check=False)
    if cpq_head and cpq_head != commits[-1]["sha"]:
        raise SystemExit("refs/cpq/head is stale; update cpq-head after rebuilding capstone-2")
    cpq_base = git("rev-parse", "--verify", "refs/cpq/base", check=False)
    if cpq_base and cpq_base != base:
        raise SystemExit("refs/cpq/base is stale; update cpq-base after queue rewrite")
    print("CPQ verification OK")


def validate_commit_msg(msg_path: Path):
    text = msg_path.read_text()
    lines = text.splitlines()
    if not lines:
        raise SystemExit("empty commit message")
    subject = lines[0].strip()
    if not (subject.startswith("cpq-") or subject.startswith("patch-")):
        return
    body = "\n".join(lines[1:]).strip()
    if not body:
        raise SystemExit("carried patch commit requires a Markdown body")
    for header in REQUIRED_HEADERS:
        if header not in body:
            raise SystemExit(f"carried patch commit is missing required section: {header}")
    if "## Upstream" in body and "PR:" not in body:
        raise SystemExit("## Upstream section must include a PR line")
    if "## Upstream" in body and "Status:" not in body:
        raise SystemExit("## Upstream section must include a Status line")


def pre_commit():
    staged = [p for p in git("diff", "--cached", "--name-only", check=False).splitlines() if p]
    touched = [p for p in staged if p in CPQ_FILES]
    if touched:
        sys.stderr.write(
            "[cpq] staged CPQ governance changes detected:\n"
            + "\n".join(f"  - {p}" for p in touched)
            + "\n[cpq] if this mutates the queue, rebuild cpq-capstone-2 last before push.\n"
        )


def main(argv):
    if len(argv) < 2:
        raise SystemExit("usage: cpq_checks.py [write-ledger|rebuild-ledger|rebuild-capstone|verify|pre-commit|commit-msg <file>]")
    cmd = argv[1]
    if cmd == "write-ledger" or cmd == "rebuild-ledger":
        write_ledger(LEDGER)
    elif cmd == "rebuild-capstone":
        rebuild_capstone()
    elif cmd == "verify":
        verify()
    elif cmd == "pre-commit":
        pre_commit()
    elif cmd == "commit-msg":
        if len(argv) != 3:
            raise SystemExit("commit-msg requires path to commit message file")
        validate_commit_msg(Path(argv[2]))
    else:
        raise SystemExit(f"unknown command: {cmd}")


if __name__ == "__main__":
    main(sys.argv)

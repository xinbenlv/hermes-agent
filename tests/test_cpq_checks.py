from scripts import cpq_checks
import pytest


def _commit(patch_id: str, sha: str | None = None):
    sha = sha or (patch_id * 4)
    return {"id": patch_id, "sha": sha, "short": sha[:8], "subject": f"{patch_id}: test"}


def test_verify_required_structural_patches_accepts_full_spine():
    commits = [
        _commit("cpq-cornerstone-0"),
        _commit("cpq-cornerstone-1"),
        _commit("patch-feat-pr9999"),
        _commit("cpq-capstone-1"),
        _commit("cpq-capstone-2"),
    ]

    cpq_checks.verify_required_structural_patches(commits)


def test_verify_required_structural_patches_rejects_missing_capstone_1():
    commits = [
        _commit("cpq-cornerstone-0"),
        _commit("cpq-cornerstone-1"),
        _commit("patch-feat-pr9999"),
        _commit("cpq-capstone-2"),
    ]

    with pytest.raises(SystemExit, match="missing required structural CPQ patches: cpq-capstone-1"):
        cpq_checks.verify_required_structural_patches(commits)


def test_verify_required_structural_patches_rejects_missing_cornerstone():
    commits = [
        _commit("cpq-cornerstone-0"),
        _commit("patch-feat-pr9999"),
        _commit("cpq-capstone-1"),
        _commit("cpq-capstone-2"),
    ]

    with pytest.raises(SystemExit, match="missing required structural CPQ patches: cpq-cornerstone-1"):
        cpq_checks.verify_required_structural_patches(commits)


def test_verify_required_structural_patches_requires_cornerstone_0_before_cornerstone_1():
    commits = [
        _commit("cpq-cornerstone-1"),
        _commit("cpq-cornerstone-0"),
        _commit("cpq-capstone-1"),
        _commit("cpq-capstone-2"),
    ]

    with pytest.raises(SystemExit, match="cpq-cornerstone-0 must appear before cpq-cornerstone-1"):
        cpq_checks.verify_required_structural_patches(commits)


def test_verify_required_structural_patches_requires_capstone_1_before_capstone_2():
    commits = [
        _commit("cpq-cornerstone-0"),
        _commit("cpq-cornerstone-1"),
        _commit("cpq-capstone-2"),
        _commit("cpq-capstone-1"),
    ]

    with pytest.raises(SystemExit, match="cpq-capstone-1 must appear before cpq-capstone-2"):
        cpq_checks.verify_required_structural_patches(commits)


def test_verify_required_structural_patches_rejects_duplicate_structural_patch_ids():
    commits = [
        _commit("cpq-cornerstone-0", sha="aaa11111"),
        _commit("cpq-cornerstone-1"),
        _commit("cpq-capstone-1"),
        _commit("cpq-capstone-1", sha="bbb22222"),
        _commit("cpq-capstone-2"),
    ]

    with pytest.raises(SystemExit, match="duplicate CPQ patch IDs in active queue: cpq-capstone-1"):
        cpq_checks.verify_required_structural_patches(commits)


def test_parse_body_frontmatter_extracts_metadata_and_markdown_body():
    metadata, body = cpq_checks.parse_body_frontmatter(
        """---\nupstream: https://example.com/pr/9999\nfiles:\n  - foo.py\n  - bar.py\nfoo: bar\n---\n\n## Summary\n- Hello\n"""
    )

    assert metadata == {
        "upstream": "https://example.com/pr/9999",
        "files": ["foo.py", "bar.py"],
        "foo": "bar",
    }
    assert body == "## Summary\n- Hello"


def test_legacy_files_list_extracts_markdown_files_section():
    files = cpq_checks.legacy_files_list(
        """## Summary\n- Hello\n\n## Files\n- `foo.py`\n- `bar.py`\n"""
    )

    assert files == ["foo.py", "bar.py"]


def test_validate_commit_message_text_accepts_frontmatter_upstream_and_files_without_why_carried():
    cpq_checks.validate_commit_message_text(
        """patch-feat-pr9999: test carry\n\n---\nupstream: https://example.com/pr/9999\nfiles:\n  - foo.py\n---\n\n## Summary\n- Adds a thing.\n\n## Drop condition\n- Drop when upstream lands.\n""",
        subject_prefix="patch-feat-pr9999:",
    )


def test_validate_commit_message_text_accepts_legacy_markdown_upstream_pr_line_and_files_section():
    cpq_checks.validate_commit_message_text(
        """patch-feat-pr9999: test carry\n\n## Upstream\n- PR: https://example.com/pr/9999\n\n## Summary\n- Adds a thing.\n\n## Drop condition\n- Drop when upstream lands.\n\n## Files\n- `foo.py`\n""",
        subject_prefix="patch-feat-pr9999:",
    )


def test_validate_commit_message_text_accepts_null_upstream_for_local_only_carry():
    cpq_checks.validate_commit_message_text(
        """cpq-capstone-1: local carry\n\n---\nupstream: null\nfiles:\n  - foo.py\n---\n\n## Summary\n- Local-only thing.\n\n## Drop condition\n- Never.\n""",
        subject_prefix="cpq-capstone-1:",
    )


def test_validate_commit_message_text_rejects_missing_upstream_metadata():
    with pytest.raises(SystemExit, match="must declare upstream via frontmatter `upstream:` or legacy `## Upstream` PR line"):
        cpq_checks.validate_commit_message_text(
            """patch-feat-pr9999: test carry\n\n---\nfiles:\n  - foo.py\n---\n\n## Summary\n- Adds a thing.\n\n## Drop condition\n- Drop when upstream lands.\n""",
            subject_prefix="patch-feat-pr9999:",
        )


def test_validate_commit_message_text_rejects_missing_files_metadata():
    with pytest.raises(SystemExit, match="must declare files via frontmatter `files:` or legacy `## Files` section"):
        cpq_checks.validate_commit_message_text(
            """patch-feat-pr9999: test carry\n\n---\nupstream: https://example.com/pr/9999\n---\n\n## Summary\n- Adds a thing.\n\n## Drop condition\n- Drop when upstream lands.\n""",
            subject_prefix="patch-feat-pr9999:",
        )


def test_validate_commit_message_text_rejects_wrong_subject_prefix():
    with pytest.raises(SystemExit, match="carried patch subject mismatch"):
        cpq_checks.validate_commit_message_text(
            """patch-feat-pr9998: test carry\n\n---\nupstream: https://example.com/pr/9998\nfiles:\n  - foo.py\n---\n\n## Summary\n- Adds a thing.\n\n## Drop condition\n- Drop when upstream lands.\n""",
            subject_prefix="patch-feat-pr9999:",
        )


def test_validate_commit_message_text_rejects_missing_required_header():
    with pytest.raises(SystemExit, match="carried patch commit is missing required section: ## Drop condition"):
        cpq_checks.validate_commit_message_text(
            """cpq-capstone-1: test carry\n\n---\nupstream: null\nfiles:\n  - foo.py\n---\n\n## Summary\n- Adds a thing.\n"""
        )


def test_verify_commit_messages_validates_each_commit_message(monkeypatch):
    commits = [
        _commit("cpq-cornerstone-0", sha="deadbeef"),
        _commit("cpq-capstone-1", sha="feedface"),
    ]
    messages = {
        "deadbeef": """cpq-cornerstone-0: first\n\n---\nupstream: null\nfiles:\n  - foo.py\n---\n\n## Summary\n- Adds a thing.\n\n## Drop condition\n- Never.\n""",
        "feedface": """cpq-capstone-1: second\n\n## Upstream\n- PR: null\n\n## Summary\n- Adds a thing.\n\n## Drop condition\n- Never.\n\n## Files\n- `bar.py`\n""",
    }

    def fake_git(*args, **kwargs):
        if args[:3] == ("show", "-s", "--format=%B"):
            return messages[args[3]]
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(cpq_checks, "git", fake_git)
    cpq_checks.verify_commit_messages(commits)


def test_append_capstone_entry_appends_when_missing(tmp_path):
    ledger = tmp_path / "carried-patch-ledger.yaml"
    ledger.write_text(
        "patches:\n"
        "  - id: cpq-cornerstone-0\n"
        "    current_commit: deadbeef\n"
        "    upstream_pr: null\n"
    )

    cpq_checks.append_capstone_entry(ledger)

    text = ledger.read_text()
    assert text.count("- id: cpq-capstone-2") == 1
    assert "current_commit: cpq-head" in text


def test_append_capstone_entry_does_not_duplicate_existing_capstone(tmp_path):
    ledger = tmp_path / "carried-patch-ledger.yaml"
    ledger.write_text(
        "patches:\n"
        "  - id: cpq-cornerstone-0\n"
        "    current_commit: deadbeef\n"
        "    upstream_pr: null\n\n"
        "  - id: cpq-capstone-2\n"
        "    current_commit: cpq-head\n"
        "    upstream_pr: null\n"
    )

    cpq_checks.append_capstone_entry(ledger)

    text = ledger.read_text()
    assert text.count("- id: cpq-capstone-2") == 1

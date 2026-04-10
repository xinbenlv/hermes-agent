"""Regression tests for Google Workspace API credential and scope validation."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills/productivity/google-workspace/scripts/google_api.py"
)


class FakeAuthorizedCredentials:
    def __init__(self, *, valid=True, expired=False, refresh_token="refresh-token"):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.refresh_calls = 0

    def refresh(self, _request):
        self.refresh_calls += 1
        self.valid = True
        self.expired = False

    def to_json(self):
        return json.dumps({
            "token": "***",
            "refresh_token": self.refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "scopes": [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/contacts.readonly",
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/documents.readonly",
            ],
        })


class FakeCredentialsFactory:
    creds = FakeAuthorizedCredentials()

    @classmethod
    def from_authorized_user_file(cls, _path, _scopes):
        return cls.creds


@pytest.fixture
def google_api_module(monkeypatch, tmp_path):
    google_module = types.ModuleType("google")
    oauth2_module = types.ModuleType("google.oauth2")
    credentials_module = types.ModuleType("google.oauth2.credentials")
    credentials_module.Credentials = FakeCredentialsFactory
    auth_module = types.ModuleType("google.auth")
    transport_module = types.ModuleType("google.auth.transport")
    requests_module = types.ModuleType("google.auth.transport.requests")
    requests_module.Request = object

    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2_module)
    monkeypatch.setitem(sys.modules, "google.oauth2.credentials", credentials_module)
    monkeypatch.setitem(sys.modules, "google.auth", auth_module)
    monkeypatch.setitem(sys.modules, "google.auth.transport", transport_module)
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", requests_module)

    spec = importlib.util.spec_from_file_location("google_workspace_api_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "TOKEN_PATH", tmp_path / "google_token.json")
    return module


def _write_token(path: Path, scopes):
    path.write_text(json.dumps({
        "token": "***",
        "refresh_token": "***",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "scopes": scopes,
    }))


# =========================================================================
# get_credentials — no longer gates on ALL scopes, just loads the token
# =========================================================================

def test_get_credentials_accepts_full_scope_token(google_api_module):
    """Token with all scopes should load fine."""
    FakeCredentialsFactory.creds = FakeAuthorizedCredentials(valid=True)
    _write_token(google_api_module.TOKEN_PATH, list(google_api_module.SCOPES))

    creds = google_api_module.get_credentials()

    assert creds is FakeCredentialsFactory.creds


def test_get_credentials_accepts_partial_scope_token(google_api_module):
    """Token with only some scopes should still load (no blanket gate)."""
    FakeCredentialsFactory.creds = FakeAuthorizedCredentials(valid=True)
    _write_token(google_api_module.TOKEN_PATH, [
        "https://www.googleapis.com/auth/gmail.readonly",
    ])

    creds = google_api_module.get_credentials()

    assert creds is FakeCredentialsFactory.creds


def test_get_credentials_rejects_missing_token(google_api_module, capsys):
    """No token file at all should exit."""
    with pytest.raises(SystemExit):
        google_api_module.get_credentials()

    err = capsys.readouterr().err
    assert "not authenticated" in err.lower()


# =========================================================================
# _check_operation_scopes — per-operation scope validation
# =========================================================================

class TestCheckOperationScopes:
    """Tests for the per-operation scope gate."""

    def test_gmail_search_allowed_with_readonly(self, google_api_module):
        """gmail.readonly is sufficient for gmail search."""
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/gmail.readonly",
        ])
        # Should not raise
        google_api_module._check_operation_scopes("gmail", "search")

    def test_gmail_search_allowed_with_modify(self, google_api_module):
        """gmail.modify is a superset that also permits gmail search."""
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/gmail.modify",
        ])
        google_api_module._check_operation_scopes("gmail", "search")

    def test_gmail_get_allowed_with_readonly(self, google_api_module):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/gmail.readonly",
        ])
        google_api_module._check_operation_scopes("gmail", "get")

    def test_gmail_send_blocked_without_send_or_modify(self, google_api_module, capsys):
        """gmail send requires gmail.send or gmail.modify."""
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/gmail.readonly",
        ])
        with pytest.raises(SystemExit):
            google_api_module._check_operation_scopes("gmail", "send")

        err = capsys.readouterr().err
        assert "gmail.send" in err
        assert "gmail.modify" in err

    def test_gmail_send_allowed_with_send_scope(self, google_api_module):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/gmail.send",
        ])
        google_api_module._check_operation_scopes("gmail", "send")

    def test_gmail_send_allowed_with_modify_scope(self, google_api_module):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/gmail.modify",
        ])
        google_api_module._check_operation_scopes("gmail", "send")

    def test_gmail_reply_blocked_without_send_or_modify(self, google_api_module, capsys):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/gmail.readonly",
        ])
        with pytest.raises(SystemExit):
            google_api_module._check_operation_scopes("gmail", "reply")

    def test_gmail_modify_blocked_without_modify(self, google_api_module, capsys):
        """gmail modify (labels) requires specifically gmail.modify."""
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
        ])
        with pytest.raises(SystemExit):
            google_api_module._check_operation_scopes("gmail", "modify")

    def test_gmail_labels_allowed_with_labels_scope(self, google_api_module):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/gmail.labels",
        ])
        google_api_module._check_operation_scopes("gmail", "labels")

    def test_calendar_list_allowed_with_readonly(self, google_api_module):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/calendar.readonly",
        ])
        google_api_module._check_operation_scopes("calendar", "list")

    def test_calendar_create_blocked_with_readonly(self, google_api_module, capsys):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/calendar.readonly",
        ])
        with pytest.raises(SystemExit):
            google_api_module._check_operation_scopes("calendar", "create")

    def test_calendar_create_allowed_with_full_scope(self, google_api_module):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/calendar",
        ])
        google_api_module._check_operation_scopes("calendar", "create")

    def test_drive_search_allowed_with_readonly(self, google_api_module):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/drive.readonly",
        ])
        google_api_module._check_operation_scopes("drive", "search")

    def test_sheets_get_allowed_with_readonly(self, google_api_module):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
        ])
        google_api_module._check_operation_scopes("sheets", "get")

    def test_sheets_update_blocked_with_readonly(self, google_api_module, capsys):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
        ])
        with pytest.raises(SystemExit):
            google_api_module._check_operation_scopes("sheets", "update")

    def test_sheets_update_allowed_with_full_scope(self, google_api_module):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/spreadsheets",
        ])
        google_api_module._check_operation_scopes("sheets", "update")

    def test_docs_get_allowed_with_readonly(self, google_api_module):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/documents.readonly",
        ])
        google_api_module._check_operation_scopes("docs", "get")

    def test_contacts_list_allowed_with_readonly(self, google_api_module):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/contacts.readonly",
        ])
        google_api_module._check_operation_scopes("contacts", "list")

    def test_unknown_operation_passes(self, google_api_module):
        """Operations not in the map should pass (fail-open, let API decide)."""
        _write_token(google_api_module.TOKEN_PATH, [])
        # Should not raise — unknown operations are not gated
        google_api_module._check_operation_scopes("unknown_service", "unknown_action")

    def test_error_message_is_actionable(self, google_api_module, capsys):
        """Error should tell user which scope to grant and how to fix it."""
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/gmail.readonly",
        ])
        with pytest.raises(SystemExit):
            google_api_module._check_operation_scopes("gmail", "send")

        err = capsys.readouterr().err
        assert "gmail send" in err.lower() or "gmail send" in err
        assert "Re-run setup.py" in err


# =========================================================================
# _granted_scopes — helper function
# =========================================================================

class TestGrantedScopes:
    def test_returns_scopes_from_list(self, google_api_module):
        _write_token(google_api_module.TOKEN_PATH, [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar",
        ])
        result = google_api_module._granted_scopes()
        assert result == {
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar",
        }

    def test_returns_empty_set_for_missing_file(self, google_api_module):
        # TOKEN_PATH doesn't exist
        result = google_api_module._granted_scopes()
        assert result == set()

    def test_returns_empty_set_for_no_scopes_key(self, google_api_module):
        google_api_module.TOKEN_PATH.write_text(json.dumps({
            "token": "***",
            "refresh_token": "***",
        }))
        result = google_api_module._granted_scopes()
        assert result == set()

    def test_handles_space_separated_scope_string(self, google_api_module):
        """Some token formats store scopes as a space-separated string."""
        google_api_module.TOKEN_PATH.write_text(json.dumps({
            "token": "***",
            "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar",
        }))
        result = google_api_module._granted_scopes()
        assert "https://www.googleapis.com/auth/gmail.readonly" in result
        assert "https://www.googleapis.com/auth/calendar" in result

from unittest.mock import MagicMock, patch

from app.connectors.google_calendar import oauth as oauth_module
from app.connectors.google_calendar.oauth import (
    _pop_pending_verifier,
    _store_pending_verifier,
    exchange_code,
    get_authorization_url,
)


def test_pkce_verifier_roundtrip():
    _store_pending_verifier("test-state", "verifier-abc")
    assert _pop_pending_verifier("test-state") == "verifier-abc"
    assert _pop_pending_verifier("test-state") is None


@patch("app.connectors.google_calendar.oauth.create_oauth_flow")
def test_exchange_code_requires_matching_state(mock_create_flow):
    mock_flow = MagicMock()
    mock_create_flow.return_value = mock_flow
    mock_flow.credentials.token = "t"
    mock_flow.credentials.refresh_token = "rt"
    mock_flow.credentials.token_uri = "https://oauth2.googleapis.com/token"
    mock_flow.credentials.client_id = "cid"
    mock_flow.credentials.client_secret = "secret"
    mock_flow.credentials.scopes = ["https://www.googleapis.com/auth/calendar.readonly"]

    _store_pending_verifier("state-1", "pkce-verifier")

    exchange_code("auth-code", state="state-1")

    mock_flow.fetch_token.assert_called_once_with(
        code="auth-code", code_verifier="pkce-verifier"
    )


@patch("app.connectors.google_calendar.oauth.create_oauth_flow")
def test_get_authorization_url_stores_verifier(mock_create_flow):
    oauth_module._pending_verifiers.clear()
    mock_flow = MagicMock()
    mock_flow.code_verifier = "stored-verifier"
    mock_create_flow.return_value = mock_flow
    mock_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth?x=1", "ignored")

    url = get_authorization_url()

    assert url.startswith("https://accounts.google.com")
    assert len(oauth_module._pending_verifiers) == 1
    stored_verifier, _ = next(iter(oauth_module._pending_verifiers.values()))
    assert stored_verifier == "stored-verifier"

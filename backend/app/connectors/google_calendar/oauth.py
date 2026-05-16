import logging
import os
import secrets
import time
from threading import Lock
from typing import Any

# Google may return extra scopes (e.g. openid, userinfo) vs what we requested.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

from app.config import get_settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# PKCE code_verifier must be reused on token exchange (oauthlib generates one per Flow).
_pending_verifiers: dict[str, tuple[str, float]] = {}
_pending_lock = Lock()
_PENDING_TTL_SECONDS = 600


def _client_config() -> dict[str, Any]:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set")
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


def create_oauth_flow() -> Flow:
    settings = get_settings()
    return Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )


def _extract_code_verifier(flow: Flow) -> str:
    # google_auth_oauthlib stores PKCE on Flow, not on oauth2session
    verifier = flow.code_verifier
    if verifier:
        return verifier
    raise ValueError("OAuth flow did not produce a PKCE code_verifier")


def _store_pending_verifier(state: str, code_verifier: str) -> None:
    expires = time.time() + _PENDING_TTL_SECONDS
    with _pending_lock:
        now = time.time()
        expired = [k for k, (_, exp) in _pending_verifiers.items() if exp < now]
        for k in expired:
            del _pending_verifiers[k]
        _pending_verifiers[state] = (code_verifier, expires)


def _pop_pending_verifier(state: str) -> str | None:
    with _pending_lock:
        entry = _pending_verifiers.pop(state, None)
    if not entry:
        return None
    code_verifier, expires = entry
    if time.time() > expires:
        return None
    return code_verifier


def get_authorization_url() -> str:
    flow = create_oauth_flow()
    state = secrets.token_urlsafe(32)
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    code_verifier = _extract_code_verifier(flow)
    _store_pending_verifier(state, code_verifier)
    logger.info("Google OAuth: started auth flow (state=%s...)", state[:8])
    return url


def exchange_code(code: str, *, state: str | None) -> dict[str, Any]:
    if not state:
        raise ValueError("Missing OAuth state parameter")

    code_verifier = _pop_pending_verifier(state)
    if not code_verifier:
        raise ValueError(
            "OAuth session expired or unknown state. Start Connect Google Calendar again."
        )

    flow = create_oauth_flow()
    flow.fetch_token(code=code, code_verifier=code_verifier)
    creds = flow.credentials
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }


def credentials_from_oauth(oauth_data: dict[str, Any]) -> Credentials:
    return Credentials(
        token=oauth_data.get("token"),
        refresh_token=oauth_data.get("refresh_token"),
        token_uri=oauth_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=oauth_data.get("client_id") or get_settings().google_client_id,
        client_secret=oauth_data.get("client_secret") or get_settings().google_client_secret,
        scopes=oauth_data.get("scopes") or SCOPES,
    )

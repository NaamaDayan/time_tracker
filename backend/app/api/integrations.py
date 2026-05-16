import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import verify_api_key
from app.config import get_settings
from app.connectors.google_calendar.oauth import exchange_code, get_authorization_url
from app.connectors.google_calendar.sync import is_google_calendar_connected
from app.connectors.sync_state import read_sync_state, write_sync_state
from app.database import get_db
from app.models import SourceAccount

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

SOURCE = "google_calendar"


def _get_google_account(db: Session) -> SourceAccount | None:
    return db.query(SourceAccount).filter(SourceAccount.source == SOURCE).first()


@router.get("/google/status", dependencies=[Depends(verify_api_key)])
def google_calendar_status(db: Session = Depends(get_db)) -> dict:
    account = _get_google_account(db)
    connected = is_google_calendar_connected(account)
    email = None
    if connected and account:
        state = read_sync_state(account)
        email = (state.get("oauth") or {}).get("email")
    return {"connected": connected, "email": email}


@router.get("/google/auth")
def google_calendar_auth() -> RedirectResponse:
    try:
        url = get_authorization_url()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return RedirectResponse(url)


@router.get("/google/callback")
def google_calendar_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    frontend = settings.frontend_url.rstrip("/")

    if error:
        return RedirectResponse(f"{frontend}/?google_error={error}")
    if not code:
        return RedirectResponse(f"{frontend}/?google_error=missing_code")
    if not state:
        return RedirectResponse(f"{frontend}/?google_error=missing_state")

    try:
        oauth_data = exchange_code(code, state=state)
    except Exception:
        logger.exception("Google OAuth token exchange failed")
        return RedirectResponse(f"{frontend}/?google_error=token_exchange")

    account = _get_google_account(db)
    if not account:
        account = SourceAccount(
            source=SOURCE,
            display_name="Google Calendar",
            config_json={},
            is_active=True,
        )
        db.add(account)
        db.flush()

    state = read_sync_state(account)
    oauth = dict(state.get("oauth") or {})
    oauth.update(oauth_data)
    write_sync_state(db, account, oauth=oauth, calendar_id=state.get("calendar_id", "primary"))

    return RedirectResponse(f"{frontend}/?google_connected=1")

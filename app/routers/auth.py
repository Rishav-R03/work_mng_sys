from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..deps import get_db
from ..models import User
from ..security import encrypt
from ..templating import templates

router = APIRouter()

oauth = OAuth()
oauth.register(
    name="github",
    client_id=config.GITHUB_CLIENT_ID,
    client_secret=config.GITHUB_CLIENT_SECRET,
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": config.GITHUB_SCOPE},
)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("uid"):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"dev_login": config.DEV_LOGIN, "configured": bool(config.GITHUB_CLIENT_ID)}
    )


@router.get("/auth/github")
async def github_login(request: Request):
    if not config.GITHUB_CLIENT_ID:
        raise HTTPException(500, "GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET are not configured.")
    return await oauth.github.authorize_redirect(request, f"{config.BASE_URL}/auth/callback")


@router.get("/auth/callback")
async def github_callback(request: Request, db: Session = Depends(get_db)):
    import logging

    from authlib.integrations.base_client.errors import MismatchingStateError
    from fastapi import HTTPException

    logger = logging.getLogger(__name__)
    session_keys = sorted(request.session.keys()) if hasattr(request, "session") else []
    callback_context = {
        "has_code": bool(request.query_params.get("code")),
        "has_state": bool(request.query_params.get("state")),
        "session_keys": session_keys,
    }

    try:
        token = await oauth.github.authorize_access_token(request)
    except MismatchingStateError as exc:
        logger.warning(
            "GitHub OAuth callback rejected because state did not match. "
            "This usually means the callback session cookie was missing, expired, "
            "or the login was started in a different browser/session. context=%s",
            callback_context,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "GitHub login could not be completed because the OAuth state did "
                "not match. Please start the login flow again."
            ),
        ) from exc
    except Exception as exc:
        logger.exception(
            "GitHub OAuth callback failed during token exchange. "
            "error_type=%s context=%s",
            type(exc).__name__,
            callback_context,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=502,
            detail=(
                "GitHub login failed while exchanging the OAuth callback for an "
                "access token. Please try again."
            ),
        ) from exc
    profile = (await oauth.github.get("user", token=token)).json()
    login = profile["login"]

    if config.ALLOWED_GITHUB_LOGINS and login.lower() not in config.ALLOWED_GITHUB_LOGINS:
        raise HTTPException(403, "This tracker is private to its owner.")

    user = db.scalar(select(User).where(User.github_id == profile["id"]))
    if not user:
        user = User(github_id=profile["id"])
        db.add(user)
    user.login = login
    user.name = profile.get("name") or login
    user.avatar_url = profile.get("avatar_url") or ""
    user.token_enc = encrypt(token["access_token"])
    db.commit()

    request.session["uid"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/dev-login")
def dev_login(request: Request, db: Session = Depends(get_db)):
    if not config.DEV_LOGIN:
        raise HTTPException(404)
    user = db.scalar(select(User).where(User.github_id == 0))
    if not user:
        user = User(github_id=0, login="demo", name="Demo Dev")
        db.add(user)
        db.commit()
    request.session["uid"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

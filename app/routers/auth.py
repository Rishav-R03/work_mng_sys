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
    token = await oauth.github.authorize_access_token(request)
    profile = (await oauth.github.get("user", token=token)).json()
    login = profile["login"]

    if config.ALLOWED_GITHUB_LOGIN and login.lower() != config.ALLOWED_GITHUB_LOGIN:
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

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import config
from .db import Base, engine
from .deps import NotAuthenticated
from .routers import auth, dashboard, entries, reports

app = FastAPI(title="Work Tracker")
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    max_age=60 * 60 * 24 * 30,
    same_site="lax",
    https_only=config.HTTPS,
)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

for r in (auth.router, dashboard.router, entries.router, reports.router):
    app.include_router(r)


@app.on_event("startup")
def create_tables() -> None:
    Base.metadata.create_all(engine)


@app.exception_handler(NotAuthenticated)
async def not_authenticated(request: Request, exc: NotAuthenticated):
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)


@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok"


@app.get("/")
def index():
    return RedirectResponse("/dashboard", status_code=303)

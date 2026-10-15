from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from .. import report_builder as rb
from .. import services as sv
from ..deps import current_user, get_db
from ..models import User
from ..templating import templates

router = APIRouter()


def _build(user, db, rng, start_s, end_s, audience):
    audience = audience if audience in ("manager", "recruiter") else "manager"
    key, start, end, label = sv.resolve_range(rng, start_s, end_s, sv.user_today(user))
    s = sv.summarize(db, user, start, end)
    return key, start, end, label, audience, rb.build(audience, user, s, start, label)


@router.get("/report", response_class=HTMLResponse)
def report(
    request: Request,
    rng: str = Query("last_month", alias="range"),
    start: str | None = None,
    end: str | None = None,
    audience: str = "manager",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    key, s_date, e_date, label, audience, md = _build(user, db, rng, start, end, audience)
    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "user": user,
            "ranges": sv.RANGES,
            "range_key": key,
            "start": s_date,
            "end": e_date,
            "label": label,
            "audience": audience,
            "markdown": md,
            "body": rb.render_html(md),
        },
    )


@router.get("/report/download")
def download(
    rng: str = Query("last_month", alias="range"),
    start: str | None = None,
    end: str | None = None,
    audience: str = "manager",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _, s_date, _, _, audience, md = _build(user, db, rng, start, end, audience)
    return Response(
        md,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={audience}-report-{s_date:%Y-%m}.md"},
    )

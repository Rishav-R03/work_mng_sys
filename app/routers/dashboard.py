import csv
import datetime as dt
import io
from zoneinfo import ZoneInfo, available_timezones

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import services as sv
from ..deps import current_user, get_db
from ..github import SyncError, sync_user
from ..models import Entry, User
from ..templating import templates

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    rng: str = Query("month", alias="range"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    today = sv.user_today(user)
    key, start, end, label = sv.resolve_range(rng, None, None, today)
    s = sv.summarize(db, user, start, end)

    # Compare with the previous period of the same length.
    length = (end - start).days + 1
    prev_end = start - dt.timedelta(days=1)
    prev = sv.summarize(db, user, prev_end - dt.timedelta(days=length - 1), prev_end)
    delta = None
    if prev["total_min"]:
        delta = round(100 * (s["total_min"] - prev["total_min"]) / prev["total_min"])

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "ranges": sv.RANGES,
            "range_key": key,
            "label": label,
            "s": s,
            "charts": sv.chart_data(s, start),
            "story": sv.headline(user, s, start),
            "delta": delta,
        },
    )


@router.post("/github/sync")
def github_sync(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        new = sync_user(db, user)
        request.session["flash"] = f"GitHub synced: {new['commit']} new commits, {new['pr']} new merged PRs."
    except SyncError as e:
        request.session["flash"] = f"Sync failed: {e}"
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse(request, "settings.html", {"user": user})


@router.post("/settings")
def save_settings(
    request: Request,
    contracted_hours: float = Form(...),
    timezone: str = Form("UTC"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not 0 < contracted_hours <= 24:
        request.session["flash"] = "Daily hours must be between 0 and 24."
    elif timezone not in available_timezones():
        request.session["flash"] = f"Unknown timezone: {timezone}"
    else:
        user.contracted_hours = contracted_hours
        user.timezone = timezone
        db.commit()
        request.session["flash"] = "Settings saved."
    return RedirectResponse("/settings", status_code=303)


@router.get("/export/entries.csv")
def export_csv(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Entry).where(Entry.user_id == user.id).order_by(Entry.date, Entry.id)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "start", "end", "minutes", "project", "description", "tags", "impact"])
    for e in rows:
        w.writerow([
            e.date, e.start_time or "", e.end_time or "", e.duration_minutes,
            e.project.name if e.project else "", e.description, e.tags, e.impact_note,
        ])
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=work-entries.csv"},
    )

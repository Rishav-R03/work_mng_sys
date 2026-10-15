import datetime as dt
import re
from collections import defaultdict

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import services as sv
from ..deps import current_user, get_db
from ..models import Entry, Project, User
from ..templating import templates

router = APIRouter()


# ---------------------------------------------------------------- parsing
def parse_duration(text: str) -> int:
    t = (text or "").strip().lower()
    err = ValueError("Enter a duration like 1.5, 1:30, 90m or 2h 15m.")
    if not t:
        raise err
    if re.fullmatch(r"\d+:\d{1,2}", t):
        h, m = t.split(":")
        return int(h) * 60 + int(m)
    if re.fullmatch(r"\d+(\.\d+)?", t):
        return round(float(t) * 60)
    m = re.fullmatch(r"(?:(\d+(?:\.\d+)?)\s*h)?\s*(?:(\d+)\s*m)?", t)
    if not m or not (m.group(1) or m.group(2)):
        raise err
    return round(float(m.group(1) or 0) * 60) + int(m.group(2) or 0)


def parse_times(mode: str, start_time: str, end_time: str, break_min: str, duration: str):
    """Return (start, end, minutes). Range mode subtracts an optional break."""
    if mode == "duration":
        start = end = None
        minutes = parse_duration(duration)
    else:
        if not start_time or not end_time:
            raise ValueError("Enter both a start and an end time.")
        start, end = dt.time.fromisoformat(start_time), dt.time.fromisoformat(end_time)
        span = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
        if span <= 0:
            span += 24 * 60  # worked past midnight
        minutes = span - (int(break_min) if break_min.strip() else 0)
    if not 0 < minutes <= 24 * 60:
        raise ValueError("Duration must be between 1 minute and 24 hours.")
    return start, end, minutes


def clean_tags(raw: str) -> str:
    seen = []
    for t in raw.replace("#", "").split(","):
        t = t.strip().lower()
        if t and t not in seen:
            seen.append(t)
    return ",".join(seen)


def get_project(db: Session, user: User, name: str) -> Project | None:
    name = name.strip()
    if not name:
        return None
    p = db.scalar(select(Project).where(Project.user_id == user.id, Project.name == name))
    if not p:
        p = Project(user_id=user.id, name=name)
        db.add(p)
        db.flush()
    return p


def _apply(db, user, entry, *, date, mode, start_time, end_time, break_min, duration, project, description, tags, impact_note):
    try:
        day = dt.date.fromisoformat(date)
    except ValueError:
        raise ValueError("Pick a valid date.")
    entry.date = day
    entry.start_time, entry.end_time, entry.duration_minutes = parse_times(mode, start_time, end_time, break_min, duration)
    entry.project_id = (p.id if (p := get_project(db, user, project)) else None)
    entry.description = description.strip()
    entry.tags = clean_tags(tags)
    entry.impact_note = impact_note.strip()


# ---------------------------------------------------------------- list rendering
def _month(month: str | None, today: dt.date) -> tuple[str, dt.date, dt.date]:
    try:
        y, m = (int(x) for x in month.split("-")) if month else (today.year, today.month)
        start, end = sv.month_bounds(y, m)
    except (ValueError, AttributeError):
        start, end = sv.month_bounds(today.year, today.month)
    return f"{start:%Y-%m}", start, end


def _list_ctx(db: Session, user: User, month: str | None, error: str | None = None, oob: bool = False) -> dict:
    today = sv.user_today(user)
    month, start, end = _month(month, today)
    entries = db.scalars(
        select(Entry).where(Entry.user_id == user.id, Entry.date >= start, Entry.date <= end)
        .order_by(Entry.date.desc(), Entry.id.desc())
    ).all()
    commits, prs = sv.activity_by_day(db, user, start, end)
    cm = round(user.contracted_hours * 60)

    grouped: dict[dt.date, list[Entry]] = defaultdict(list)
    for e in entries:
        grouped[e.date].append(e)
    days = []
    for d, es in grouped.items():
        total = sum(e.duration_minutes for e in es)
        days.append({"date": d, "entries": es, "total": total, "overtime": max(0, total - cm),
                     "commits": commits.get(d, 0), "prs": prs.get(d, 0)})

    return {
        "user": user,
        "month": month,
        "month_label": start.strftime("%B %Y"),
        "prev_month": f"{(start - dt.timedelta(days=1)):%Y-%m}",
        "next_month": f"{(end + dt.timedelta(days=1)):%Y-%m}",
        "days": days,
        "month_total": sum(d["total"] for d in days),
        "month_overtime": sum(d["overtime"] for d in days),
        "error": error,
        "oob": oob,
    }


def _list_response(request, db, user, month, error=None):
    return templates.TemplateResponse(request, "_entries_list.html", _list_ctx(db, user, month, error, oob=True))


def _owned(db: Session, user: User, entry_id: int) -> Entry:
    e = db.get(Entry, entry_id)
    if not e or e.user_id != user.id:
        raise HTTPException(404)
    return e


# ---------------------------------------------------------------- routes
@router.get("/entries", response_class=HTMLResponse)
def entries_page(request: Request, month: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ctx = _list_ctx(db, user, month)
    ctx.update(
        today=sv.user_today(user),
        projects=db.scalars(select(Project.name).where(Project.user_id == user.id).order_by(Project.name)).all(),
        entry=None,
    )
    return templates.TemplateResponse(request, "entries.html", ctx)


@router.get("/entries/list", response_class=HTMLResponse)
def entries_list(request: Request, month: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "_entries_list.html", _list_ctx(db, user, month))


@router.post("/entries", response_class=HTMLResponse)
def create_entry(
    request: Request,
    date: str = Form(...), mode: str = Form("range"),
    start_time: str = Form(""), end_time: str = Form(""), break_min: str = Form(""), duration: str = Form(""),
    project: str = Form(""), description: str = Form(""), tags: str = Form(""), impact_note: str = Form(""),
    month: str = Form(""),
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    entry = Entry(user_id=user.id)
    try:
        _apply(db, user, entry, date=date, mode=mode, start_time=start_time, end_time=end_time, break_min=break_min,
               duration=duration, project=project, description=description, tags=tags, impact_note=impact_note)
    except ValueError as e:
        db.rollback()
        return _list_response(request, db, user, month, str(e))
    db.add(entry)
    db.commit()
    return _list_response(request, db, user, month)


@router.get("/entries/{entry_id}/edit", response_class=HTMLResponse)
def edit_form(request: Request, entry_id: int, month: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    entry = _owned(db, user, entry_id)
    projects = db.scalars(select(Project.name).where(Project.user_id == user.id).order_by(Project.name)).all()
    return templates.TemplateResponse(request, "_entry_edit.html", {"entry": entry, "month": month, "projects": projects, "error": None})


@router.post("/entries/{entry_id}", response_class=HTMLResponse)
def update_entry(
    request: Request, entry_id: int,
    date: str = Form(...), mode: str = Form("range"),
    start_time: str = Form(""), end_time: str = Form(""), break_min: str = Form(""), duration: str = Form(""),
    project: str = Form(""), description: str = Form(""), tags: str = Form(""), impact_note: str = Form(""),
    month: str = Form(""),
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    entry = _owned(db, user, entry_id)
    try:
        _apply(db, user, entry, date=date, mode=mode, start_time=start_time, end_time=end_time, break_min=break_min,
               duration=duration, project=project, description=description, tags=tags, impact_note=impact_note)
    except ValueError as e:
        db.rollback()
        projects = db.scalars(select(Project.name).where(Project.user_id == user.id).order_by(Project.name)).all()
        return templates.TemplateResponse(request, "_entry_edit.html", {"entry": entry, "month": month, "projects": projects, "error": str(e)})
    db.commit()
    resp = _list_response(request, db, user, month)
    resp.headers["HX-Retarget"] = "#entries-list"
    resp.headers["HX-Reswap"] = "innerHTML"
    return resp


@router.delete("/entries/{entry_id}", response_class=HTMLResponse)
def delete_entry(request: Request, entry_id: int, month: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_owned(db, user, entry_id))
    db.commit()
    return _list_response(request, db, user, month)

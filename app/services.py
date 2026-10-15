"""Core calculations: date ranges, overtime, summaries, chart data and the one-line story."""

import calendar
import datetime as dt
from collections import Counter, defaultdict
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Activity, Entry, User

RANGES = [
    ("month", "This month"),
    ("last_month", "Last month"),
    ("30d", "Last 30 days"),
    ("90d", "Last 90 days"),
    ("year", "Last 12 months"),
]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------------------------------------------------------------- time helpers
def get_tz(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone)
    except Exception:
        return ZoneInfo("UTC")


def user_today(user: User) -> dt.date:
    return dt.datetime.now(get_tz(user)).date()


def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    return dt.date(year, month, 1), dt.date(year, month, calendar.monthrange(year, month)[1])


def resolve_range(key: str, start_s: str | None, end_s: str | None, today: dt.date):
    """Return (key, start, end, label). `end` may be in the future (current month)."""
    labels = dict(RANGES)
    if key == "custom" and start_s and end_s:
        try:
            start, end = dt.date.fromisoformat(start_s), dt.date.fromisoformat(end_s)
            if start <= end:
                return "custom", start, end, f"{start:%d %b %Y} – {end:%d %b %Y}"
        except ValueError:
            pass
    if key == "last_month":
        end = today.replace(day=1) - dt.timedelta(days=1)
        start, end = month_bounds(end.year, end.month)
    elif key == "30d":
        start, end = today - dt.timedelta(days=29), today
    elif key == "90d":
        start, end = today - dt.timedelta(days=89), today
    elif key == "year":
        start, end = today - dt.timedelta(days=364), today
    else:
        key = "month"
        start, end = month_bounds(today.year, today.month)
    label = start.strftime("%B %Y") if key in ("month", "last_month") else labels[key]
    return key, start, end, label


def weekdays_between(start: dt.date, end: dt.date) -> int:
    n, d = 0, start
    while d <= end:
        n += d.weekday() < 5
        d += dt.timedelta(days=1)
    return n


def fmt_hm(minutes: int | float) -> str:
    minutes = int(round(minutes))
    h, m = divmod(abs(minutes), 60)
    sign = "-" if minutes < 0 else ""
    if m == 0:
        return f"{sign}{h}h"
    return f"{sign}{h}h {m:02d}m"


def hours(minutes: int | float) -> float:
    return round(minutes / 60, 1)


# ---------------------------------------------------------------- GitHub activity
def load_activity(db: Session, user: User, start: dt.date, end: dt.date) -> list[tuple[Activity, dt.date]]:
    """Activity in [start, end], paired with its date in the user's timezone."""
    tz = get_tz(user)
    lo = dt.datetime.combine(start - dt.timedelta(days=1), dt.time.min)
    hi = dt.datetime.combine(end + dt.timedelta(days=2), dt.time.min)
    rows = db.scalars(
        select(Activity).where(Activity.user_id == user.id, Activity.occurred_at >= lo, Activity.occurred_at < hi)
    ).all()
    out = []
    for a in rows:
        local = a.occurred_at.replace(tzinfo=dt.timezone.utc).astimezone(tz).date()
        if start <= local <= end:
            out.append((a, local))
    return out


def activity_by_day(db: Session, user: User, start: dt.date, end: dt.date):
    commits, prs = Counter(), Counter()
    for a, d in load_activity(db, user, start, end):
        (commits if a.kind == "commit" else prs)[d] += 1
    return commits, prs


# ---------------------------------------------------------------- summary
def summarize(db: Session, user: User, start: dt.date, end: dt.date) -> dict:
    today = user_today(user)
    end_eff = min(end, today)
    cm = round(user.contracted_hours * 60)

    entries = db.scalars(
        select(Entry).where(Entry.user_id == user.id, Entry.date >= start, Entry.date <= end).order_by(Entry.date, Entry.id)
    ).all()

    daily: dict[dt.date, int] = defaultdict(int)
    projects: dict[str, int] = defaultdict(int)
    tags: dict[str, int] = defaultdict(int)
    by_weekday = [0] * 7
    for e in entries:
        m = e.duration_minutes
        daily[e.date] += m
        projects[e.project.name if e.project else "Unassigned"] += m
        for t in e.tag_list:
            tags[t] += m
        by_weekday[e.date.weekday()] += m

    total = sum(daily.values())
    overtime_days = sorted((d, m - cm) for d, m in daily.items() if m > cm)
    overtime = sum(m for _, m in overtime_days)

    acts = load_activity(db, user, start, end_eff)
    commits = [(a, d) for a, d in acts if a.kind == "commit"]
    prs = sorted(((a, d) for a, d in acts if a.kind == "pr"), key=lambda x: x[1], reverse=True)

    wins = [
        {"date": e.date, "project": e.project.name if e.project else "Unassigned", "note": e.impact_note.strip()}
        for e in entries
        if e.impact_note.strip()
    ]
    wins.sort(key=lambda w: w["date"], reverse=True)
    seen: set[tuple[str, str]] = set()  # same note logged on several days -> keep the latest
    wins = [w for w in wins if not ((k := (w["project"], w["note"])) in seen or seen.add(k))]

    return {
        "entries": entries,
        "contracted_min": cm,
        "daily": dict(daily),
        "days_worked": len(daily),
        "total_min": total,
        "overtime_min": overtime,
        "overtime_days": overtime_days,
        "expected_min": cm * weekdays_between(start, end_eff),
        "avg_min": total / len(daily) if daily else 0,
        "projects": sorted(projects.items(), key=lambda kv: kv[1], reverse=True),
        "tags": sorted(tags.items(), key=lambda kv: kv[1], reverse=True),
        "by_weekday": by_weekday,
        "wins": wins,
        "commit_count": len(commits),
        "pr_count": len(prs),
        "prs": prs,
        "commits_by_day": Counter(d for _, d in commits),
        "prs_by_day": Counter(d for _, d in prs),
        "repos": Counter(a.repo for a, _ in acts).most_common(8),
        "end_eff": end_eff,
    }


def chart_data(s: dict, start: dt.date) -> dict:
    cm, end = s["contracted_min"], s["end_eff"]
    days = max((end - start).days + 1, 0)
    weekly = days > 92

    buckets: dict[dt.date, dict] = {}
    d = start
    while d <= end:
        key = d - dt.timedelta(days=d.weekday()) if weekly else d
        b = buckets.setdefault(key, {"reg": 0, "ot": 0, "commits": 0, "prs": 0})
        m = s["daily"].get(d, 0)
        b["reg"] += min(m, cm)
        b["ot"] += max(0, m - cm)
        b["commits"] += s["commits_by_day"].get(d, 0)
        b["prs"] += s["prs_by_day"].get(d, 0)
        d += dt.timedelta(days=1)

    keys = sorted(buckets)
    return {
        "labels": [(f"Wk {k:%d %b}" if weekly else f"{k:%d %b}") for k in keys],
        "regular": [hours(buckets[k]["reg"]) for k in keys],
        "overtime": [hours(buckets[k]["ot"]) for k in keys],
        "commits": [buckets[k]["commits"] for k in keys],
        "prs": [buckets[k]["prs"] for k in keys],
        "weekly": weekly,
        "project_labels": [p for p, _ in s["projects"]],
        "project_hours": [hours(m) for _, m in s["projects"]],
        "weekday_labels": WEEKDAYS,
        "weekday_hours": [hours(m) for m in s["by_weekday"]],
    }


def headline(user: User, s: dict, start: dt.date) -> str:
    """One plain-English sentence summarising the period."""
    if not s["entries"]:
        return "No work logged for this period yet."
    end = s["end_eff"]
    n_proj = len(s["projects"])
    text = (
        f"From {start:%d %b} to {end:%d %b %Y} you logged {hours(s['total_min'])} hours "
        f"across {n_proj} project{'s' if n_proj != 1 else ''} on {s['days_worked']} days"
    )
    if s["overtime_min"]:
        text += (
            f", including {hours(s['overtime_min'])} hours of overtime on {len(s['overtime_days'])} "
            f"day{'s' if len(s['overtime_days']) != 1 else ''} beyond the {user.contracted_hours:g}h schedule"
        )
    text += "."
    if s["commit_count"] or s["pr_count"]:
        text += f" On GitHub that came with {s['commit_count']} commits and {s['pr_count']} merged pull requests."
    if s["projects"]:
        top, mins = s["projects"][0]
        if s["total_min"]:
            text += f" Most of your time ({round(100 * mins / s['total_min'])}%) went to {top}."
    return text

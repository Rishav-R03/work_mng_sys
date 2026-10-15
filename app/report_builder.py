"""Builds the two "story" reports (manager / recruiter) as Markdown from the same data."""

import datetime as dt
import html
from collections import defaultdict

import markdown

from . import services as sv
from .models import User


def _clean(text: str) -> str:
    return " ".join(text.split()).replace("[", "(").replace("]", ")").replace("|", "/")


def build_manager(user: User, s: dict, start: dt.date, label: str) -> str:
    name = user.name or user.login
    cm_h = user.contracted_hours
    lines = [
        f"# Work report — {label}",
        f"*{name} · {start:%d %b %Y} to {s['end_eff']:%d %b %Y}*",
        "",
        sv.headline(user, s, start),
        "",
        "## At a glance",
        f"- **Hours logged:** {sv.hours(s['total_min'])} (scheduled: {sv.hours(s['expected_min'])})",
        f"- **Overtime:** {sv.hours(s['overtime_min'])} h on {len(s['overtime_days'])} days (anything beyond {cm_h:g} h/day)",
        f"- **Days worked:** {s['days_worked']} · average {sv.hours(s['avg_min'])} h per working day",
        f"- **GitHub:** {s['commit_count']} commits, {s['pr_count']} merged pull requests across {len(s['repos'])} repos",
        "",
    ]
    if s["projects"]:
        lines += ["## Where the time went", "", "| Project | Hours | Share |", "|---|---:|---:|"]
        for p, m in s["projects"]:
            share = round(100 * m / s["total_min"]) if s["total_min"] else 0
            lines.append(f"| {_clean(p)} | {sv.hours(m)} | {share}% |")
        lines.append("")
    if s["overtime_days"]:
        lines += ["## Overtime days", "", "| Date | Hours worked | Overtime |", "|---|---:|---:|"]
        for d, ot in s["overtime_days"]:
            lines.append(f"| {d:%a %d %b} | {sv.hours(s['daily'][d])} | +{sv.hours(ot)} |")
        lines.append("")
    if s["wins"]:
        lines += ["## Delivered"]
        lines += [f"- **{_clean(w['project'])}** ({w['date']:%d %b}): {_clean(w['note'])}" for w in s["wins"][:12]]
        lines.append("")
    if s["prs"]:
        lines += ["## Merged pull requests"]
        lines += [f"- [{_clean(a.title)}]({a.url}) — {a.repo}" for a, _ in s["prs"][:10]]
        lines.append("")
    return "\n".join(lines)


def build_recruiter(user: User, s: dict, start: dt.date, label: str) -> str:
    name = user.name or user.login
    lines = [f"# {name} — Engineering highlights", f"*{label}*", ""]

    if s["wins"]:
        lines += ["## Impact"]
        lines += [f"- {_clean(w['note'])} *({_clean(w['project'])})*" for w in s["wins"][:10]]
        lines.append("")

    by_project: dict[str, list] = defaultdict(list)
    for e in s["entries"]:
        by_project[e.project.name if e.project else "Unassigned"].append(e)
    if by_project:
        lines += ["## Projects"]
        order = [p for p, _ in s["projects"]]
        for p in order:
            es = by_project[p]
            notes = list(dict.fromkeys(_clean(e.impact_note) for e in es if e.impact_note.strip()))
            if not notes:  # fall back to the biggest pieces of work
                big = sorted((e for e in es if e.description.strip()), key=lambda e: e.duration_minutes, reverse=True)
                notes = list(dict.fromkeys(_clean(e.description) for e in big))[:3]
            tags = sorted({t for e in es for t in e.tag_list})
            lines.append(f"### {_clean(p)}")
            if tags:
                lines.append(f"*Tech: {', '.join(tags)}*")
            lines += [f"- {n}" for n in notes[:5]] or ["- Ongoing development work"]
            lines.append("")

    if s["tags"]:
        lines += ["## Technologies & focus areas", ", ".join(t for t, _ in s["tags"][:15]), ""]

    if s["commit_count"] or s["pr_count"]:
        lines += [
            "## GitHub contributions",
            f"{s['commit_count']} commits and {s['pr_count']} merged pull requests across {len(s['repos'])} repositories.",
            "",
        ]
        lines += [f"- [{_clean(a.title)}]({a.url}) — {a.repo}" for a, _ in s["prs"][:10]]
        lines.append("")
    return "\n".join(lines)


def build(audience: str, user: User, s: dict, start: dt.date, label: str) -> str:
    return (build_recruiter if audience == "recruiter" else build_manager)(user, s, start, label)


def render_html(md: str) -> str:
    """Escape first so GitHub-sourced text can't inject markup, then render Markdown."""
    safe = html.escape(md, quote=False)
    out = markdown.markdown(safe, extensions=["tables"])
    return out.replace("<table>", '<table class="table table-sm table-striped w-auto">')

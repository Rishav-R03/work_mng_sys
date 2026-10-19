"""Pull commits and merged PRs for the signed-in user via the GitHub search API."""

import datetime as dt
import time

import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Activity, User
from .security import decrypt

API = "https://api.github.com"
INITIAL_DAYS = 365
SPACING = 2.2  # seconds between requests: search allows ~30/min, and bursts trip the secondary limit
BUDGET = 80  # seconds per sync; Render drops requests that run past ~100s


class SyncError(Exception):
    pass


class OutOfBudget(Exception):
    """Out of time, or GitHub told us to wait longer than we can. Progress so far is kept."""


def _month_windows(since: dt.date, until: dt.date):
    """Yield (start, end) windows of at most one month so each stays under the 1000-result search cap."""
    start = since
    while start <= until:
        nxt = (start.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        end = min(nxt - dt.timedelta(days=1), until)
        yield start, end
        start = nxt


def _limit_wait(r: httpx.Response) -> float | None:
    """Seconds GitHub wants us to wait if this response is a rate limit, else None."""
    if "retry-after" in r.headers:
        return int(r.headers["retry-after"]) + 1
    if r.headers.get("X-RateLimit-Remaining") == "0":
        return max(int(r.headers.get("X-RateLimit-Reset", "0")) - time.time(), 1) + 1
    if "rate limit" in r.text.lower():
        return 60  # secondary limit without a hint: GitHub advises waiting at least a minute
    return None


class _Github:
    def __init__(self, client: httpx.Client, deadline: float):
        self.client, self.deadline, self._last = client, deadline, 0.0

    def get(self, path: str, params: dict) -> dict:
        for attempt in range(3):
            gap = SPACING - (time.monotonic() - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.monotonic()
            r = self.client.get(f"{API}{path}", params=params)
            if r.status_code == 401:
                raise SyncError("GitHub rejected the stored token. Sign out and sign in again.")
            if r.status_code in (403, 429) and (wait := _limit_wait(r)) is not None:
                if attempt == 2 or time.monotonic() + wait > self.deadline:
                    raise OutOfBudget()
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                raise SyncError(f"GitHub API error {r.status_code}: {r.text[:200]}")
            return r.json()
        raise OutOfBudget()

    def search(self, path: str, query: str, sort: str):
        for page in range(1, 11):
            items = self.get(path, {"q": query, "per_page": 100, "page": page, "sort": sort}).get("items", [])
            yield from items
            if len(items) < 100:
                return


def _parse_ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(tzinfo=None)


def _store(db: Session, user: User, rows: list[tuple], existing: set, new: dict) -> None:
    for kind, ext_id, repo, title, url, when in rows:
        if (kind, ext_id) in existing:
            continue
        existing.add((kind, ext_id))
        db.add(Activity(user_id=user.id, kind=kind, ext_id=ext_id, repo=repo, title=title, url=url, occurred_at=when))
        new[kind] += 1


def sync_user(db: Session, user: User) -> dict:
    """Returns {"commit": n, "pr": n, "partial": bool}. Progress is saved after every step, so a
    partial sync (rate limit or time budget) is resumed by simply syncing again."""
    try:
        token = decrypt(user.token_enc)
    except (InvalidToken, ValueError):
        raise SyncError("Stored GitHub token can't be read. Sign out and sign in again.")

    today = dt.date.today()
    if user.last_synced_at:
        since = user.last_synced_at.date() - dt.timedelta(days=3)  # overlap; inserts are de-duplicated
    else:
        since = today - dt.timedelta(days=INITIAL_DAYS)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    existing = set(db.execute(select(Activity.kind, Activity.ext_id).where(Activity.user_id == user.id)).all())
    new = {"commit": 0, "pr": 0, "partial": False}

    with httpx.Client(timeout=30, headers=headers) as client:
        gh = _Github(client, time.monotonic() + BUDGET)
        try:
            prs = []
            for it in gh.search("/search/issues", f"author:{user.login} type:pr is:merged merged:{since}..{today}", "updated"):
                merged = (it.get("pull_request") or {}).get("merged_at") or it.get("closed_at")
                if merged:
                    repo = "/".join(it["repository_url"].split("/")[-2:])
                    prs.append(("pr", f"{repo}#{it['number']}", repo, it["title"][:300], it["html_url"], _parse_ts(merged)))
            _store(db, user, prs, existing, new)
            db.commit()

            for w_start, w_end in _month_windows(since, today):
                commits = [
                    (
                        "commit", it["sha"], it["repository"]["full_name"],
                        it["commit"]["message"].split("\n")[0][:300], it["html_url"],
                        _parse_ts(it["commit"]["author"]["date"]),
                    )
                    for it in gh.search("/search/commits", f"author:{user.login} author-date:{w_start}..{w_end}", "author-date")
                ]
                _store(db, user, commits, existing, new)
                # Window finished: remember how far we got so a retry resumes here.
                user.last_synced_at = (
                    dt.datetime.utcnow() if w_end >= today
                    else dt.datetime.combine(w_end, dt.time.max)
                )
                db.commit()
        except OutOfBudget:
            db.commit()
            new["partial"] = True
    return new

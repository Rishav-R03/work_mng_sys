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


class SyncError(Exception):
    pass


def _month_windows(since: dt.date, until: dt.date):
    """Yield (start, end) windows of at most one month so each stays under the 1000-result search cap."""
    start = since
    while start <= until:
        nxt = (start.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        end = min(nxt - dt.timedelta(days=1), until)
        yield start, end
        start = nxt


def _get(client: httpx.Client, path: str, params: dict) -> dict:
    for attempt in range(2):
        r = client.get(f"{API}{path}", params=params)
        if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0" and attempt == 0:
            reset = int(r.headers.get("X-RateLimit-Reset", "0"))
            time.sleep(min(max(reset - time.time(), 1), 65))
            continue
        if r.status_code == 401:
            raise SyncError("GitHub rejected the stored token. Sign out and sign in again.")
        if r.status_code >= 400:
            raise SyncError(f"GitHub API error {r.status_code}: {r.text[:200]}")
        return r.json()
    raise SyncError("GitHub rate limit hit. Try again in a minute.")


def _search(client: httpx.Client, path: str, query: str, sort: str):
    page = 1
    while page <= 10:
        data = _get(client, path, {"q": query, "per_page": 100, "page": page, "sort": sort})
        items = data.get("items", [])
        yield from items
        if len(items) < 100:
            return
        page += 1


def _parse_ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc).replace(tzinfo=None)


def sync_user(db: Session, user: User) -> dict:
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
    found: list[tuple[str, str, str, str, str, dt.datetime]] = []  # kind, ext_id, repo, title, url, when
    with httpx.Client(timeout=30, headers=headers) as client:
        for w_start, w_end in _month_windows(since, today):
            span = f"{w_start}..{w_end}"
            for it in _search(client, "/search/commits", f"author:{user.login} author-date:{span}", "author-date"):
                found.append((
                    "commit",
                    it["sha"],
                    it["repository"]["full_name"],
                    it["commit"]["message"].split("\n")[0][:300],
                    it["html_url"],
                    _parse_ts(it["commit"]["author"]["date"]),
                ))
            for it in _search(client, "/search/issues", f"author:{user.login} type:pr is:merged merged:{span}", "updated"):
                merged = (it.get("pull_request") or {}).get("merged_at") or it.get("closed_at")
                if not merged:
                    continue
                repo = "/".join(it["repository_url"].split("/")[-2:])
                found.append(("pr", f"{repo}#{it['number']}", repo, it["title"][:300], it["html_url"], _parse_ts(merged)))

    existing = set(db.execute(select(Activity.kind, Activity.ext_id).where(Activity.user_id == user.id)).all())
    new = {"commit": 0, "pr": 0}
    for kind, ext_id, repo, title, url, when in found:
        if (kind, ext_id) in existing:
            continue
        existing.add((kind, ext_id))
        db.add(Activity(user_id=user.id, kind=kind, ext_id=ext_id, repo=repo, title=title, url=url, occurred_at=when))
        new[kind] += 1
    user.last_synced_at = dt.datetime.utcnow()
    db.commit()
    return new

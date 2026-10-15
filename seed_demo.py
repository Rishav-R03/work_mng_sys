"""Fill the local DB with ~120 days of fake work + GitHub activity for the demo user (local testing only)."""

import datetime as dt
import random

from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.models import Activity, Entry, Project, User

random.seed(7)
Base.metadata.create_all(engine)
db = SessionLocal()

user = db.scalar(select(User).where(User.github_id == 0)) or User(github_id=0, login="demo", name="Demo Dev")
user.timezone = "Asia/Kolkata"
db.add(user)
db.commit()
for model in (Entry, Activity, Project):
    for row in db.scalars(select(model).where(model.user_id == user.id)):
        db.delete(row)
db.commit()

projects = {n: Project(user_id=user.id, name=n) for n in ("Payments API", "Internal Dashboard", "Data Pipeline")}
db.add_all(projects.values())
db.commit()

work = {
    "Payments API": (["python", "fastapi", "postgres"], ["Built refund endpoint", "Fixed idempotency bug", "Added webhook retries"]),
    "Internal Dashboard": (["react", "typescript"], ["Implemented filters", "Chart performance pass", "Accessibility fixes"]),
    "Data Pipeline": (["airflow", "sql", "python"], ["Backfill job", "Optimised slow query", "Added data-quality checks"]),
}
wins = {
    "Fixed idempotency bug": "Removed duplicate charges: ~40 failed-payment tickets/month dropped to 0",
    "Optimised slow query": "Cut nightly pipeline runtime from 52 min to 9 min",
    "Chart performance pass": "Dashboard load time down 60% (4.1s to 1.6s)",
}

today = dt.date.today()
for i in range(120):
    d = today - dt.timedelta(days=i)
    if d.weekday() >= 5 and random.random() > 0.12:
        continue
    if random.random() < 0.06:
        continue
    total_h = random.choice([7, 7.5, 8, 8, 8.5, 9, 9.5, 10, 11])
    remaining = total_h
    while remaining > 0:
        chunk = min(remaining, random.choice([2, 3, 4]))
        name = random.choice(list(projects))
        tags, tasks = work[name]
        task = random.choice(tasks)
        db.add(Entry(
            user_id=user.id, date=d, duration_minutes=int(chunk * 60), project_id=projects[name].id,
            description=task, tags=",".join(random.sample(tags, 2)),
            impact_note=wins.get(task, "") if random.random() < 0.5 else "",
        ))
        remaining -= chunk
    for _ in range(random.randint(0, 6)):
        when = dt.datetime.combine(d, dt.time(random.randint(4, 14), random.randint(0, 59)))  # UTC
        sha = f"{random.getrandbits(160):040x}"
        repo = random.choice(["demo/payments-api", "demo/dashboard", "demo/pipeline"])
        db.add(Activity(user_id=user.id, kind="commit", ext_id=sha, repo=repo, title=random.choice(sum((t for _, t in work.values()), [])), url=f"https://github.com/{repo}/commit/{sha}", occurred_at=when))
    if random.random() < 0.25:
        repo = random.choice(["demo/payments-api", "demo/dashboard", "demo/pipeline"])
        n = random.randint(1, 900)
        db.add(Activity(user_id=user.id, kind="pr", ext_id=f"{repo}#{n}", repo=repo, title=f"{random.choice(sum((t for _, t in work.values()), []))} (#{n})", url=f"https://github.com/{repo}/pull/{n}", occurred_at=dt.datetime.combine(d, dt.time(9, 0))))
db.commit()
print("seeded demo user with entries and activity")

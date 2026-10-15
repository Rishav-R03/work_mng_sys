import datetime as dt

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(Integer, unique=True)
    login: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200), default="")
    avatar_url: Mapped[str] = mapped_column(String(500), default="")
    token_enc: Mapped[str] = mapped_column(Text, default="")
    contracted_hours: Mapped[float] = mapped_column(Float, default=8.0)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    last_synced_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    start_time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String(300), default="")  # comma-separated, lowercase
    impact_note: Mapped[str] = mapped_column(Text, default="")

    project: Mapped[Project | None] = relationship(lazy="joined")

    @property
    def tag_list(self) -> list[str]:
        return [t for t in self.tags.split(",") if t]


class Activity(Base):
    """A commit or merged PR pulled from GitHub, used as evidence next to logged hours."""

    __tablename__ = "activity"
    __table_args__ = (UniqueConstraint("user_id", "kind", "ext_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # "commit" | "pr"
    ext_id: Mapped[str] = mapped_column(String(200))  # sha, or "owner/repo#123"
    repo: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(500))
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)  # naive UTC

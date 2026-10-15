from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import User


class NotAuthenticated(Exception):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if not user:
        raise NotAuthenticated()
    return user

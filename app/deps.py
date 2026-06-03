"""Shared FastAPI dependencies for auth and the current user."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.security import read_session_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Resolve the logged-in user from the signed session cookie, or None."""
    token = request.cookies.get(get_settings().session_cookie)
    user_id = read_session_token(token)
    if user_id is None:
        return None
    return db.query(User).filter(User.id == user_id).first()

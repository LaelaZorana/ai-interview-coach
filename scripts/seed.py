"""Seed a demo user with one pre-generated, partly-scored interview session.

Idempotent: running it twice won't create duplicate users or sessions. Invoked
by `make demo` so the app opens with something to look at immediately. The same
seed logic also powers the one-click "/demo" route (see app/services.py).

Demo credentials:  demo@interviewcoach.dev / demopass123
"""
from __future__ import annotations

from app import services
from app.database import SessionLocal, init_db
from app.llm import get_provider


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        existed = services.get_user_by_email(db, services.DEMO_EMAIL) is not None
        user = services.ensure_demo_user(db, get_provider())
        if existed:
            print(
                f"Demo user already present: {services.DEMO_EMAIL} / {services.DEMO_PASSWORD}"
            )
        else:
            print(f"Created demo user: {services.DEMO_EMAIL} / {services.DEMO_PASSWORD}")
        sessions = services.list_sessions(db, user)
        print(f"Demo has {len(sessions)} session(s) ready.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

"""InterviewCoach: FastAPI application factory and routes.

A single deployable service: FastAPI + Jinja2 + htmx, SQLite via SQLAlchemy.
Question generation and answer scoring both go through the LLM provider
interface, which defaults to a deterministic offline stub when no key is set.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import __version__, services
from app.config import get_settings
from app.database import get_db, init_db
from app.deps import get_current_user
from app.llm import build_provider, get_provider
from app.models import User
from app.rubric import AXES
from app.security import make_session_token

BASE_DIR = Path(__file__).resolve().parent
GITHUB_URL = "https://github.com/LaelaZorana/ai-interview-coach"

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["axes"] = AXES
templates.env.globals["version"] = __version__
templates.env.globals["github_url"] = GITHUB_URL


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db()
        yield

    app = FastAPI(
        title="InterviewCoach",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    # -- helpers ------------------------------------------------------------

    def require_user(user: Optional[User]) -> User:
        if user is None:
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        return user

    def render(request: Request, name: str, **ctx) -> HTMLResponse:
        ctx.setdefault("provider_name", settings.llm_provider)
        ctx.setdefault("using_real_llm", settings.using_real_llm)
        return templates.TemplateResponse(request, name, ctx)

    def _set_session_cookie(resp: RedirectResponse, user: User) -> None:
        resp.set_cookie(
            settings.session_cookie,
            make_session_token(user.id),
            max_age=settings.session_max_age,
            httponly=True,
            samesite="lax",
        )

    # -- public pages -------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, user: Optional[User] = Depends(get_current_user)):
        if user:
            return RedirectResponse("/dashboard", status_code=303)
        return render(
            request,
            "index.html",
            demo_email=services.DEMO_EMAIL,
            demo_password=services.DEMO_PASSWORD,
        )

    @app.get("/health")
    def health():
        return {"status": "ok", "provider": settings.llm_provider}

    @app.get("/demo")
    def demo(db: Session = Depends(get_db)):
        """One-click, no-keys demo: seed (if needed) and log in as the demo user.

        Lets a visitor land straight inside the product on a session that already
        has a scored answer, so the full flow is visible in a single click.
        """
        user = services.ensure_demo_user(db, get_provider())
        resp = RedirectResponse("/dashboard", status_code=303)
        _set_session_cookie(resp, user)
        return resp

    # -- auth ---------------------------------------------------------------

    @app.get("/signup", response_class=HTMLResponse)
    def signup_form(request: Request):
        return render(request, "signup.html", error=None)

    @app.post("/signup")
    def signup(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(get_db),
    ):
        email = email.strip().lower()
        if len(password) < 8:
            return render(request, "signup.html", error="Password must be at least 8 characters.")
        if services.get_user_by_email(db, email):
            return render(request, "signup.html", error="That email is already registered.")
        user = services.create_user(db, email, password)
        resp = RedirectResponse("/dashboard", status_code=303)
        _set_session_cookie(resp, user)
        return resp

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return render(request, "login.html", error=None)

    @app.post("/login")
    def login(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(get_db),
    ):
        user = services.authenticate(db, email, password)
        if not user:
            return render(request, "login.html", error="Invalid email or password.")
        resp = RedirectResponse("/dashboard", status_code=303)
        _set_session_cookie(resp, user)
        return resp

    @app.post("/logout")
    def logout():
        resp = RedirectResponse("/", status_code=303)
        resp.delete_cookie(settings.session_cookie)
        return resp

    # -- dashboard ----------------------------------------------------------

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(
        request: Request,
        user: Optional[User] = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if user is None:
            return RedirectResponse("/login", status_code=303)
        sessions = services.list_sessions(db, user)
        return render(
            request,
            "dashboard.html",
            user=user,
            sessions=sessions,
            stats=services.dashboard_stats(sessions),
            active="dashboard",
        )

    # -- create a session ---------------------------------------------------

    @app.get("/sessions/new", response_class=HTMLResponse)
    def new_session_form(
        request: Request, user: Optional[User] = Depends(get_current_user)
    ):
        if user is None:
            return RedirectResponse("/login", status_code=303)
        return render(
            request,
            "new_session.html",
            user=user,
            active="new",
            sample_jd=services.SAMPLE_JD,
        )

    @app.post("/sessions")
    def create_session(
        request: Request,
        job_description: str = Form(...),
        question_count: int = Form(5),
        user: Optional[User] = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if len(job_description.strip()) < 20:
            return render(
                request,
                "new_session.html",
                user=user,
                active="new",
                sample_jd=services.SAMPLE_JD,
                error="Please paste a fuller job description (at least 20 characters).",
            )
        question_count = max(1, min(10, question_count))
        session = services.create_session(
            db, user, job_description, get_provider(), question_count
        )
        return RedirectResponse(f"/sessions/{session.id}", status_code=303)

    # -- run a session ------------------------------------------------------

    @app.get("/sessions/{session_id}", response_class=HTMLResponse)
    def view_session(
        session_id: int,
        request: Request,
        user: Optional[User] = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if user is None:
            return RedirectResponse("/login", status_code=303)
        session = services.get_session(db, user, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        answers = [
            {
                "row": a,
                "axes": services.decode_axes(a),
                "strengths": services.decode_list(a.strengths_json),
                "improvements": services.decode_list(a.improvements_json),
            }
            for a in session.answers
        ]
        return render(
            request,
            "session.html",
            user=user,
            session=session,
            answers=answers,
            sample_answer=services.SAMPLE_ANSWER,
            active="dashboard",
        )

    @app.post("/answers/{answer_id}/score", response_class=HTMLResponse)
    def score_answer(
        answer_id: int,
        request: Request,
        answer_text: str = Form(...),
        user: Optional[User] = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        answer = services.get_answer(db, user, answer_id)
        if not answer:
            raise HTTPException(status_code=404, detail="Answer not found")
        if not answer_text.strip():
            raise HTTPException(status_code=400, detail="Answer cannot be empty")

        services.score_and_save_answer(db, answer, answer_text, get_provider())
        # Return just the scored card; htmx swaps it into place.
        return render(
            request,
            "_answer_card.html",
            user=user,
            item={
                "row": answer,
                "axes": services.decode_axes(answer),
                "strengths": services.decode_list(answer.strengths_json),
                "improvements": services.decode_list(answer.improvements_json),
            },
            session=answer.session,
        )

    return app


app = create_app()


# Keep the provider cache consistent if settings change between processes.
def reset_provider_cache() -> None:  # pragma: no cover - utility
    get_provider.cache_clear()
    build_provider()

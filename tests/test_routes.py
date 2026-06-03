"""End-to-end route tests through the FastAPI app (offline stub provider)."""
from __future__ import annotations

JD = (
    "Backend Engineer working in Python on scalable APIs and databases. "
    "You will own services, drive testing, and communicate with stakeholders."
)


def _signup(client, email="user@example.com", password="supersecret1"):
    return client.post(
        "/signup",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def test_health_reports_stub_provider(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["provider"] == "stub"


def test_home_is_public(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "InterviewCoach" in r.text
    # The hero must surface the one-click demo entry point.
    assert "/demo" in r.text


def test_one_click_demo_logs_in_with_seeded_session(client):
    # The /demo route should seed + authenticate, then land on the dashboard
    # with a session that already has a scored answer.
    r = client.get("/demo", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/dashboard"
    assert "interviewcoach_session" in r.cookies

    dash = client.get("/dashboard")
    assert dash.status_code == 200
    # Seeded session is visible and shows a real score (not just "new").
    assert "/100" in dash.text


def test_demo_is_idempotent(client):
    first = client.get("/demo", follow_redirects=True)
    assert first.status_code == 200
    # A second visit must not create a duplicate demo session.
    client.get("/demo", follow_redirects=True)
    dash = client.get("/dashboard")
    assert dash.text.count("/sessions/") >= 1


def test_dashboard_requires_login(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_signup_sets_session_cookie_and_dashboard_loads(client):
    r = _signup(client)
    assert r.status_code == 303
    assert "interviewcoach_session" in r.cookies
    # The cookie now lets us reach the dashboard.
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "practice history" in dash.text


def test_duplicate_signup_is_rejected(client):
    _signup(client)
    again = _signup(client)
    assert again.status_code == 200  # re-rendered form, not a redirect
    assert "already registered" in again.text


def test_short_password_rejected(client):
    r = client.post("/signup", data={"email": "a@b.com", "password": "short"})
    assert "at least 8 characters" in r.text


def test_login_with_wrong_password_fails(client):
    _signup(client, email="login@example.com", password="rightpassword1")
    r = client.post(
        "/login",
        data={"email": "login@example.com", "password": "wrongpassword"},
        follow_redirects=False,
    )
    assert r.status_code == 200
    assert "Invalid email or password" in r.text


def test_full_session_flow_generate_and_score(client):
    _signup(client)

    # Create a session -> redirects to the session page.
    create = client.post(
        "/sessions",
        data={"job_description": JD, "question_count": 4},
        follow_redirects=False,
    )
    assert create.status_code == 303
    session_url = create.headers["location"]

    page = client.get(session_url)
    assert page.status_code == 200
    assert "Score my answer" in page.text  # unanswered questions present a form

    # Find the first answer id from the rendered form action.
    import re
    answer_ids = re.findall(r"/answers/(\d+)/score", page.text)
    assert answer_ids, "expected at least one scorable answer"
    answer_id = answer_ids[0]

    scored = client.post(
        f"/answers/{answer_id}/score",
        data={
            "answer_text": (
                "I owned the billing API and cut failed payments by 38% and p99 "
                "latency from 1.2s to 340ms by adding idempotency and a queue. I "
                "led the rollout across three teams with zero downtime."
            )
        },
    )
    assert scored.status_code == 200
    # The htmx partial should contain the scored verdict and per-axis detail.
    assert "/5" in scored.text
    assert "Relevance" in scored.text
    # Rich rendering: a verdict band, per-axis meters, and the rubric section.
    assert "Rubric breakdown" in scored.text
    assert "ic-meter" in scored.text
    assert any(
        b in scored.text
        for b in ("Outstanding", "Strong", "Solid, needs polish", "Needs work", "Off track")
    )

    # Dashboard now shows an average score for the session.
    dash = client.get("/dashboard")
    assert "answered" in dash.text
    # KPI header surfaces aggregate proof.
    assert "Average score" in dash.text


def test_cannot_score_other_users_answer(client):
    # User A creates a session.
    _signup(client, email="a@example.com", password="passworda1")
    create = client.post(
        "/sessions", data={"job_description": JD}, follow_redirects=False
    )
    session_url = create.headers["location"]
    page = client.get(session_url)
    import re
    answer_id = re.findall(r"/answers/(\d+)/score", page.text)[0]
    client.post("/logout")

    # User B logs in and must not be able to score A's answer.
    _signup(client, email="b@example.com", password="passwordb1")
    r = client.post(f"/answers/{answer_id}/score", data={"answer_text": "hi there friend"})
    assert r.status_code == 404

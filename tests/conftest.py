"""Shared pytest fixtures.

The environment (temp SQLite DB, forced stub provider, test secret) is set
*before* the application package is imported, so every module captures the test
settings exactly once. Each test then gets a clean schema via drop_all/create_all
on the single shared engine — no fragile module reloading.
"""
from __future__ import annotations

import os
import tempfile

import pytest

# --- configure the environment before importing the app ---------------------
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="interviewcoach_test_")
os.close(_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["LLM_PROVIDER"] = "stub"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)

from app import main  # noqa: E402
from app.database import Base, engine  # noqa: E402


def pytest_unconfigure(config):  # cleanup the temp DB file at the end of the run
    try:
        os.remove(_DB_PATH)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Ensure no test leaks a cached Settings built from temporarily-patched env."""
    import app.config as config

    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.fixture()
def app_module():
    """Reset the schema before each test for full isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return main


@pytest.fixture()
def client(app_module):
    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as c:
        yield c

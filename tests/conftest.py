from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault(
    "JOBHUNT_DATABASE_URL",
    "sqlite:////tmp/jobhunt-web-pytest/jobhunt.sqlite3",
)
os.environ.setdefault("JOBHUNT_COOKIE_SECURE", "false")
os.environ.setdefault(
    "JOBHUNT_SECRET_KEY",
    "pytest-secret-key-with-at-least-32-characters",
)
os.environ.setdefault("JOBHUNT_DEVELOPMENT_RUNNER", "true")
os.environ.setdefault("JOBHUNT_DEVELOPMENT_ROOT", "/tmp/jobhunt-web-pytest/users")
os.environ.setdefault("JOBHUNT_STAGING_ROOT", "/tmp/jobhunt-web-pytest/staging")

import pytest

from webapp.db import Base, engine


@pytest.fixture(autouse=True)
def clean_database():
    Path("/tmp/jobhunt-web-pytest").mkdir(parents=True, exist_ok=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

"""Nox sessions for matrix testing across Python versions.

Run all default sessions:
    uv run nox

Run tests against a single Python version:
    uv run nox -s tests-3.14
"""

from __future__ import annotations

import nox

nox.options.default_venv_backend = "uv"
nox.options.reuse_existing_virtualenvs = True
nox.options.sessions = ["tests"]

PYTHON_VERSIONS = ["3.11", "3.12", "3.13", "3.14"]


@nox.session(python=PYTHON_VERSIONS)
def tests(session: nox.Session) -> None:
    """Run the test suite against a single Python version."""
    session.run_install(
        "uv",
        "sync",
        "--active",
        "--group=dev",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    session.run("pytest", *session.posargs)


@nox.session(python=PYTHON_VERSIONS[-1])
def tests_duckdb(session: nox.Session) -> None:
    """Run the test suite with the optional duckdb engine installed."""
    session.run_install(
        "uv",
        "sync",
        "--active",
        "--group=dev",
        "--extra=duckdb",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    session.run("pytest", *session.posargs)

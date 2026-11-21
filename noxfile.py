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

PYTHON_VERSIONS = ["3.10", "3.11", "3.12", "3.13", "3.14", "3.15"]


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


@nox.session(python=PYTHON_VERSIONS[-1])
def eval(session: nox.Session) -> None:
    """Check the efficiency eval against evals/baseline.json, and that the handbook is fresh."""
    session.run_install(
        "uv",
        "sync",
        "--active",
        "--group=dev",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    session.run("python", "scripts/gen_handbook.py", "--check")
    session.run("python", "scripts/eval.py", "--check")


MCP_LIBRARIES = {"mcp1": "mcp>=1.10,<2", "mcp2": "mcp>=2,<3", "fastmcp": "fastmcp>=2.10"}


@nox.session(python=[PYTHON_VERSIONS[0], PYTHON_VERSIONS[-1]])
@nox.parametrize("library", list(MCP_LIBRARIES))
def tests_mcp(session: nox.Session, library: str) -> None:
    """Register the MCP tool on a real server, once per MCP library."""
    session.run_install(
        "uv",
        "sync",
        "--active",
        "--group=dev",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    session.install(MCP_LIBRARIES[library])
    session.run(
        "pytest",
        "tests/test_mcp_contract.py",
        "tests/test_mcp.py",
        "-o",
        "addopts=--strict-markers -v",
        *session.posargs,
    )

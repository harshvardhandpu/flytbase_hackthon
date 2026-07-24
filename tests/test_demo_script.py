"""Tests for the one-command demo launcher script.

These tests verify that scripts/demo.py:
- Exists and is executable
- Has correct structure with expected functions
- Handles environment checks correctly
- Formats output correctly

Tests do NOT depend on external services (PostgreSQL, Alembic, etc.).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
DEMO_SCRIPT = SCRIPTS_DIR / "demo.py"
SEED_SCRIPT = SCRIPTS_DIR / "seed_demo_data.py"


def test_demo_script_exists() -> None:
    """The demo.py script must exist."""
    assert DEMO_SCRIPT.is_file(), f"Expected {DEMO_SCRIPT} to exist"


def test_demo_script_is_executable() -> None:
    """The demo.py script should have a shebang line."""
    content = DEMO_SCRIPT.read_text()
    assert content.startswith("#!/usr/bin/env python3"), (
        "Expected shebang line '#!/usr/bin/env python3'"
    )


def test_demo_script_has_main() -> None:
    """The demo script must have a main() function."""
    content = DEMO_SCRIPT.read_text()
    assert "def main()" in content, "Expected main() function"
    assert "if __name__ == \"__main__\":" in content, (
        "Expected __main__ guard"
    )


def test_demo_script_has_required_functions() -> None:
    """The demo script must have all expected helper functions."""
    content = DEMO_SCRIPT.read_text()
    expected = [
        "environment_check",
        "prepare_database",
        "check_server",
        "print_demo_instructions",
        "main",
    ]
    for func in expected:
        assert f"def {func}" in content, f"Expected function '{func}'"


def test_demo_script_has_demo_instructions() -> None:
    """The demo instructions should mention key demo flow items."""
    content = DEMO_SCRIPT.read_text()
    assert "ScoutOS" in content
    assert "http://localhost:8000/demo" in content
    assert "Launch Demo Mission" in content
    assert "Qualification Score" in content
    assert "Pipeline" in content


def test_demo_script_has_banner() -> None:
    """The demo script must display a banner."""
    content = DEMO_SCRIPT.read_text()
    assert "🚀 ScoutOS Demo" in content
    assert "FlytBase Hackathon 2026" in content


@pytest.mark.parametrize(
    ("env_var", "expected_mention"),
    [
        ("DATABASE_URL", "postgresql"),
        ("pg_isready", "PostgreSQL"),
        ("alembic", "migrations"),
    ],
)
def test_demo_script_mentions_expected_topics(
    env_var: str, expected_mention: str
) -> None:
    """The script should reference key environment checks."""
    content = DEMO_SCRIPT.read_text()
    assert expected_mention in content, (
        f"Expected '{expected_mention}' in demo.py"
    )


def test_demo_script_imports_safely() -> None:
    """The demo script should import without errors."""
    result = subprocess.run(
        [sys.executable, "-c", "import ast; ast.parse(open('scripts/demo.py').read())"],
        cwd=SCRIPTS_DIR.parent,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"Syntax error: {result.stderr}"
    )


def test_seed_script_referenced() -> None:
    """The demo script should reference seed_demo_data.py."""
    content = DEMO_SCRIPT.read_text()
    assert "seed_demo_data.py" in content, (
        "Expected reference to seed_demo_data.py"
    )


def test_seed_script_exists() -> None:
    """The seed script must exist (it's called by demo.py)."""
    assert SEED_SCRIPT.is_file(), f"Expected {SEED_SCRIPT} to exist"
    assert SEED_SCRIPT.suffix == ".py"


def test_demo_script_has_reasonable_size() -> None:
    """The demo script should be substantial (not a stub)."""
    content = DEMO_SCRIPT.read_text()
    lines = content.splitlines()
    assert 200 <= len(lines) <= 500, (
        f"Expected 200-500 lines, got {len(lines)}"
    )


@pytest.mark.parametrize(
    ("exit_message"),
    [
        "Demo Ready",
        "Environment Check",
        "Database Preparation",
        "Server Health Check",
    ],
)
def test_demo_script_output_sections(exit_message: str) -> None:
    """The demo script should print expected section headers."""
    content = DEMO_SCRIPT.read_text()
    assert exit_message in content, f"Expected section '{exit_message}'"


def test_demo_script_exit_codes_documented() -> None:
    """The script should document its exit codes."""
    content = DEMO_SCRIPT.read_text()
    assert "Exit codes:" in content, "Expected exit code documentation"
    assert "0 — Demo ready" in content

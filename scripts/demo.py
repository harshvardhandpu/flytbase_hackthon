#!/usr/bin/env python3
"""
ScoutOS — One-Command Demo Launcher

Verifies the environment, prepares the database, checks the server,
and prints demo instructions for the FlytBase Hackathon 2026.

Usage:
    python scripts/demo.py

Exit codes:
    0 — Demo ready
    1 — Environment issue (Python, venv, DB, etc.)
"""

from __future__ import annotations

import http.client
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path

# ── Constants ───────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUIRED_PYTHON = (3, 12)
BANNER = """
{bar}
  🚀 ScoutOS Demo
  AI-Powered BDR Operating System
  FlytBase Hackathon 2026
{bar}
""".replace(
    "{bar}",
    "=" * 59,
).strip()


# ── Helpers ─────────────────────────────────────────────────────────────


def _print_step(step: str, status: str, detail: str = "") -> None:
    icon = {"ok": chr(0x2705), "skip": chr(0x23ED) + chr(0xFE0F),
            "fail": chr(0x274C), "info": chr(0x2139) + chr(0xFE0F)}.get(status, "  ")
    line = f"  {icon}  {step}"
    if detail:
        line += " \u2014 " + detail
    print(line)


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd or PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _check_python_version() -> bool:
    version = sys.version_info[:2]
    if version >= REQUIRED_PYTHON:
        _print_step("Python version", "ok", f"{version[0]}.{version[1]}")
        return True
    _print_step(
        "Python version", "fail",
        f"Need {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+, got {version[0]}.{version[1]}",
    )
    return False


def _check_venv() -> tuple[bool, str | None]:
    venv_dir = PROJECT_ROOT / ".venv"
    venv_exists = venv_dir.is_dir() and (venv_dir / "bin" / "python").exists()
    in_venv = sys.prefix != sys.base_prefix

    if in_venv:
        _print_step("Virtual environment", "ok", "active")
        return True, sys.executable
    if venv_exists:
        python_path = str(venv_dir / "bin" / "python")
        _print_step("Virtual environment", "skip", "found at .venv (not activated)")
        return True, python_path
    _print_step(
        "Virtual environment", "fail",
        "not found. Create with: python -m venv .venv",
    )
    return False, None


def _check_env_file() -> bool:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        _print_step(".env file", "ok")
        return True
    _print_step(".env file", "skip", "not found. Copy from .env.example")
    return False


def _check_postgres() -> bool:
    pg_isready = shutil.which("pg_isready")
    if pg_isready:
        result = _run([pg_isready])
        if result.returncode == 0:
            _print_step("PostgreSQL", "ok")
            return True

    # Fallback: socket check
    try:
        sock = socket.create_connection(("localhost", 5432), timeout=3)
        sock.close()
        _print_step("PostgreSQL", "ok", "localhost:5432")
        return True
    except OSError:
        _print_step(
            "PostgreSQL", "fail",
            "Ensure PostgreSQL is running (sudo systemctl start postgresql)",
        )
        return False


# ── Main steps ──────────────────────────────────────────────────────────


def environment_check(python_path: str) -> bool:
    print()
    print("  Environment Check")
    print()

    ok_py = _check_python_version()
    ok_venv, _ = _check_venv()
    ok_env = _check_env_file()
    ok_pg = _check_postgres()

    critical = [ok_py, ok_venv, ok_pg]
    if not ok_env:
        _print_step(
            "Warning", "info",
            "No .env file. Copy .env.example to .env if needed.",
        )

    if all(critical):
        _print_step("Environment", "ok", "all critical checks passed")
        return True

    print()
    print("  Environment checks failed. Fix the issues above and try again.")
    if not ok_py:
        print(f"     Install Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+")
    if not ok_venv:
        print("     Create venv: python -m venv .venv && source .venv/bin/activate")
        print("     Install deps: pip install -e .")
    if not ok_pg:
        print("     Start PostgreSQL: sudo systemctl start postgresql")
        print("     Create DB: createdb scoutos")
    return False


def prepare_database(python_path: str) -> bool:
    print()
    print("  Database Preparation")
    print()

    # Alembic migrations
    if shutil.which("alembic"):
        alembic_cmd = ["alembic"]
    else:
        alembic_cmd = [python_path, "-m", "alembic"]

    _print_step("Running database migrations", "info")
    result = _run([*alembic_cmd, "upgrade", "head"])
    if result.returncode == 0:
        _print_step("Alembic migrations", "ok")
    else:
        error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        if "no such table" in error.lower() or "already exists" in error.lower():
            _print_step("Alembic migrations", "skip", "tables already exist")
        else:
            _print_step("Alembic migrations", "fail", error)
            return False

    # Seed demo data
    _print_step("Seeding demo data", "info")
    result = _run([python_path, str(PROJECT_ROOT / "scripts" / "seed_demo_data.py")])
    if result.returncode == 0:
        _print_step("Demo data", "ok")
        return True

    error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
    _print_step("Demo data", "fail", error)
    return False


def check_server() -> bool:
    print()
    print("  Server Health Check")
    print()

    conn = None
    try:
        conn = http.client.HTTPConnection("localhost", 8000, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        data = json.loads(resp.read().decode())

        if resp.status == 200 and data.get("status") == "ok":
            _print_step("Server health", "ok", "running on http://localhost:8000")
            return True
        _print_step("Server health", "fail", f"unexpected response: {resp.status}")
        return False
    except (ConnectionRefusedError, TimeoutError, OSError) as exc:
        _print_step("Server health", "fail", f"server not reachable: {exc}")
        return False
    except json.JSONDecodeError:
        _print_step("Server health", "fail", "invalid response from /health")
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass


def print_demo_instructions() -> None:
    print()
    print("=" * 56)
    print("  ScoutOS Demo Ready")
    print("=" * 56)
    print()
    print("   Open in your browser:")
    print()
    print("   http://localhost:8000/demo")
    print()
    print("   Demo Flow (3 minutes):")
    print()
    print("   +---------------------------------------+")
    print("   |  Demo Page  (/demo)                   |")
    print("   |      |-- Click Launch Demo Mission     |")
    print("   +---------------------------------------+")
    print("   |  Mission Control Dashboard            |")
    print("   |      |                                 |")
    print("   |  SkyGrid Lead Detail                  |")
    print("   |  - Company Profile (320 employees)    |")
    print("   |  - Qualification Score (91/100)       |")
    print("   |  - Outreach Draft (approved)          |")
    print("   |  - Pipeline (Meeting Scheduled)       |")
    print("   |      |                                 |")
    print("   |  Inbound Reply (Sarah Chen, COO)      |")
    print("   |      |                                 |")
    print("   |  Pipeline Kanban                      |")
    print("   |      |                                 |")
    print("   |  Activity Timeline                    |")
    print("   +---------------------------------------+")
    print()
    print("   Key talking points for judges:")
    print("   - 5 specialized AI agents (Research to Pipeline)")
    print("   - Provider-neutral AI (swap models via config)")
    print("   - Human approval boundary (no auto-sending)")
    print("   - 185+ tests passing")
    print("   - 5 demo companies with complete lifecycle data")
    print()
    print("   ScoutOS - Built for FlytBase Hackathon 2026")
    print()


def main() -> int:
    print(BANNER)

    # Step 1: Environment check
    _, python_path = _check_venv()
    python = python_path or sys.executable

    if not environment_check(python):
        return 1

    # Step 2: Database preparation
    if not prepare_database(python):
        return 1

    # Step 3: Server check
    server_ok = check_server()
    if not server_ok:
        print()
        print("   Server is not running.")
        print()
        print("   Start it with:")
        print()
        print("   uvicorn app.main:app --host 0.0.0.0 --port 8000")
        print()
        print("   Then run this script again to verify.")
        print()

    # Step 4: Instructions
    print_demo_instructions()

    return 0 if server_ok else 1


if __name__ == "__main__":
    sys.exit(main())

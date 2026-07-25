"""Tests for BHP demo seed data (structure + idempotency keys)."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

SEED_PATH = Path(__file__).resolve().parent.parent / "scripts" / "seed_demo_data.py"


def _load_seed_module():
    """Load seed_demo_data without executing main (imports app.db)."""
    spec = importlib.util.spec_from_file_location("seed_demo_data", SEED_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 — may fail without DB deps in CI
        pytest.skip(f"Could not import seed_demo_data: {exc}")
    return module


def test_seed_script_parses() -> None:
    source = SEED_PATH.read_text()
    ast.parse(source)


def test_seed_contains_bhp_company_and_inbound() -> None:
    source = SEED_PATH.read_text()
    assert '"name": "BHP"' in source or "'name': 'BHP'" in source
    assert "bhp.com" in source
    assert "james.anderson@bhp.com" in source
    assert "Exploring AI-powered drone automation for mining operations" in source
    assert "AI-powered drone automation solutions for our mining" in source


def test_seed_bhp_structures_when_importable() -> None:
    mod = _load_seed_module()

    companies = {c["name"]: c for c in mod.COMPANIES}
    assert "BHP" in companies
    bhp = companies["BHP"]
    assert bhp["domain"] == "bhp.com"
    assert bhp["industry"] == "Mining"

    profile = bhp["profile_data"]
    assert profile["recent_signals"], "BHP must seed recent_signals"
    assert profile["operational_pain_points"], "BHP must seed operational_pain_points"
    assert profile["buying_signals"], "BHP must seed buying_signals"

    for sig in profile["recent_signals"]:
        assert "title" in sig and "url" in sig and "summary" in sig
        assert "category" in sig and "source_type" in sig
        assert "example.com" not in sig["url"]
        assert "linkedin.com" not in sig["url"]

    for pain in profile["operational_pain_points"]:
        assert pain.get("pain_point") and pain.get("source_url")

    for buy in profile["buying_signals"]:
        assert buy.get("signal") and buy.get("source_url")

    leads = {ld["company_name"]: ld for ld in mod.LEADS_DATA}
    assert leads["BHP"]["contact_email"] == "james.anderson@bhp.com"
    assert leads["BHP"]["contact_name"] == "James Anderson"

    quals = {q["company_name"]: q for q in mod.QUALIFICATION_DATA}
    assert quals["BHP"]["overall_score"] >= 80
    assert quals["BHP"]["priority"] == "HOT"

    inbound = [m for m in mod.INBOUND_MESSAGES if m["company_name"] == "BHP"]
    assert len(inbound) == 1
    assert inbound[0]["subject"].startswith("Exploring AI-powered drone")
    assert inbound[0]["from_email"] == "james.anderson@bhp.com"


def test_seed_idempotency_guards_present() -> None:
    """Seed must skip existing companies and inbound (from_email + subject)."""
    source = SEED_PATH.read_text()
    assert "already exists, skipping" in source
    assert "from_email" in source
    assert "InboundMessage.subject" in source or "subject ==" in source

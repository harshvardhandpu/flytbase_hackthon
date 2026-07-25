"""Detect stale / unusable ResearchReport payloads for cache reuse.

Inbound simulate must NOT reuse reports that predate the enterprise BDR
schema or that contain blocked social sources / raw article dumps.

This module is intentionally pure (no DB) so it is easy to unit-test and
safe to import from the API router and seed scripts.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

# ── Blocked social / placeholder hosts ─────────────────────────────────
# Matched against URL hostnames (not free-text false positives like box.com).
_BLOCKED_HOSTS: frozenset[str] = frozenset(
    {
        "linkedin.com",
        "lnkd.in",
        "x.com",
        "twitter.com",
        "t.co",
        "facebook.com",
        "fb.com",
        "instagram.com",
        "example.com",
        "example.org",
        "example.net",
    }
)

# Free-text fragments for non-host-ambiguous domains only.
# NOTE: never match bare "x.com" as a substring — it false-positives on box.com.
_BLOCKED_TEXT_FRAGMENTS: tuple[str, ...] = (
    "linkedin.com",
    "://linkedin.",
    "twitter.com",
    "facebook.com",
    "instagram.com",
    "example.com",
    "example.org",
    "example.net",
    "://x.com/",
    "://x.com?",
    "://www.x.com/",
)

# New enterprise research schema keys (any missing → stale).
_REQUIRED_FINDING_KEYS: tuple[str, ...] = (
    "company_overview",
    "latest_news",
    "operational_pain_points",
    "buying_signals",
    "recent_signals",
    "evidence",
)

# Heuristics for "article dump" / markdown noise
_MARKDOWN_DUMP_RE = re.compile(
    r"(```|#{1,6}\s|\*\*[^*]{8,}|\[[^\]]{3,}\]\([^)]+\)|\|[-:]+\|)",
    re.MULTILINE,
)
_RAW_CHUNK_RE = re.compile(
    r"(Answer:|Sources?:|Content:|Raw content|tavily|snippet:|"
    r"Future Outlook|Translating |AI Infrastructure|Continue reading)",
    re.IGNORECASE,
)

_MAX_STRUCTURED_TEXT_LEN = 250


def _hostname(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _host_is_blocked(host: str) -> bool:
    if not host:
        return False
    if host in _BLOCKED_HOSTS:
        return True
    # Subdomains: au.linkedin.com, mobile.twitter.com
    return any(host.endswith("." + blocked) for blocked in _BLOCKED_HOSTS)


def _url_is_blocked(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    lower = url.lower().strip()
    host = _hostname(lower)
    if _host_is_blocked(host):
        return True
    # Bare host-less strings / non-parseable URLs
    for frag in _BLOCKED_TEXT_FRAGMENTS:
        if frag in lower:
            return True
    # Host token "linkedin" (au.linkedin.com already covered by suffix)
    if host == "linkedin" or host.endswith(".linkedin"):
        return True
    return False


def _iter_url_candidates(findings: dict[str, Any], sources_col: Any) -> list[str]:
    """Collect every URL-like string from findings + report.sources column."""
    urls: list[str] = []

    def _add(u: Any) -> None:
        if u is None:
            return
        s = str(u).strip()
        if s:
            urls.append(s)

    def _from_item(item: Any) -> None:
        if isinstance(item, str):
            _add(item)
        elif isinstance(item, dict):
            _add(item.get("url"))
            _add(item.get("source_url"))
            # Nested citation shapes
            _add(item.get("source"))

    for item in findings.get("sources") or []:
        _from_item(item)

    for key in (
        "recent_signals",
        "latest_news",
        "business_signals",
        "evidence",
        "operational_pain_points",
        "buying_signals",
    ):
        for item in findings.get(key) or []:
            _from_item(item)

    for item in sources_col or []:
        _from_item(item)

    return urls


def _collect_urls(report_like: Any) -> list[str]:
    findings = getattr(report_like, "findings", None) or {}
    if not isinstance(findings, dict):
        findings = {}
    sources_col = getattr(report_like, "sources", None) or []
    return _iter_url_candidates(findings, sources_col)


def _urls_contain_blocked(urls: list[str]) -> bool:
    return any(_url_is_blocked(u) for u in urls)


def _text_is_raw_dump(text: str) -> bool:
    if not text:
        return False
    if len(text) > _MAX_STRUCTURED_TEXT_LEN:
        return True
    if _MARKDOWN_DUMP_RE.search(text):
        return True
    if _RAW_CHUNK_RE.search(text):
        return True
    # Multi-paragraph article-like blocks
    if text.count("\n") >= 4 and len(text) > 180:
        return True
    return False


def _pain_points_too_raw(findings: dict[str, Any]) -> bool:
    items: list[Any] = []
    for key in ("pain_points", "operational_pain_points"):
        raw = findings.get(key) or []
        if isinstance(raw, list):
            items.extend(raw)

    for item in items:
        if isinstance(item, str):
            if _text_is_raw_dump(item):
                return True
            continue
        if isinstance(item, dict):
            for field in ("pain_point", "evidence", "summary", "signal"):
                val = item.get(field)
                if isinstance(val, str) and _text_is_raw_dump(val):
                    return True
    return False


def _buying_signals_are_dumps(findings: dict[str, Any]) -> bool:
    for item in findings.get("buying_signals") or []:
        if isinstance(item, str):
            if _text_is_raw_dump(item):
                return True
            continue
        if isinstance(item, dict):
            for field in ("signal", "evidence", "summary", "title"):
                val = item.get(field)
                if isinstance(val, str) and _text_is_raw_dump(val):
                    return True
    return False


def _missing_schema_keys(findings: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in _REQUIRED_FINDING_KEYS:
        if key not in findings:
            missing.append(key)
            continue
        # company_overview must be a non-empty dict with a description somewhere
        if key == "company_overview":
            overview = findings.get("company_overview")
            if not isinstance(overview, dict):
                missing.append("company_overview_invalid")
            elif not (overview.get("description") or findings.get("description")):
                missing.append("company_overview_empty")
    return missing


def is_stale_research_report(report: Any) -> bool:
    """Return True when a cached ResearchReport must not be reused."""
    if report is None:
        return False

    findings = getattr(report, "findings", None) or {}
    if not isinstance(findings, dict):
        findings = {}

    urls = _collect_urls(report)

    if _urls_contain_blocked(urls):
        return True

    if _missing_schema_keys(findings):
        return True

    if _pain_points_too_raw(findings):
        return True

    if _buying_signals_are_dumps(findings):
        return True

    if urls and all(_url_is_blocked(u) or "example.com" in u.lower() for u in urls):
        return True

    return False


def stale_reason(report: Any) -> str:
    """Machine-readable reason list for logs (never includes secrets)."""
    if report is None:
        return "none"

    findings = getattr(report, "findings", None) or {}
    if not isinstance(findings, dict):
        findings = {}

    urls = _collect_urls(report)
    reasons: list[str] = []

    blocked = [u for u in urls if _url_is_blocked(u)]
    if blocked:
        # Surface host only — never full query strings with tokens
        hosts = sorted({_hostname(u) or "unknown" for u in blocked})[:5]
        reasons.append("blocked_sources:" + "|".join(hosts))

    missing = _missing_schema_keys(findings)
    if missing:
        reasons.append("missing_schema:" + "|".join(missing))

    if _pain_points_too_raw(findings):
        reasons.append("raw_pain_points")

    if _buying_signals_are_dumps(findings):
        reasons.append("dump_buying_signals")

    if urls and all("example.com" in u.lower() for u in urls):
        reasons.append("all_example_sources")

    return ",".join(reasons) if reasons else "unknown"

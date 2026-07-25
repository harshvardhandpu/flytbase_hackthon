"""Post-synthesis normalization for ResearchAgent findings.

Cleans LLM output (and evidence-based fallbacks) so BDR reports do not
contain raw Tavily article dumps, markdown, or multi-source mashups.

Does not call the network or modify SignalCollector / cache logic.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.intelligence.signal_collector import ResearchSignal

logger = logging.getLogger(__name__)

_MAX_FIELD_LEN = 240
_MAX_EVIDENCE_LEN = 220
_MAX_TITLE_LEN = 160

_MARKDOWN_RE = re.compile(
    r"(```|#{1,3}\s|\*\*[^*]{4,}|\[[^\]]+\]\([^)]+\)|^\s*[-*]\s)",
    re.MULTILINE,
)
_WS_RE = re.compile(r"\s+")

# Operational themes relevant to FlytBase (drone fleet automation)
_PAIN_KEYWORDS: tuple[str, ...] = (
    "inspect",
    "safety",
    "monitor",
    "remote",
    "manual",
    "risk",
    "hazard",
    "inefficien",
    "scale",
    "operat",
    "surveil",
    "stockpile",
    "drone",
    "automat",
    "visibility",
    "exposure",
    "compliance",
    "throughput",
    "coordination",
    "workforce",
)

_BUYING_KEYWORDS: tuple[str, ...] = (
    "invest",
    "automat",
    "autonomous",
    "ai ",
    " a.i",
    "artificial intelligence",
    "digital",
    "transform",
    "expand",
    "expansion",
    "partner",
    "deploy",
    "technology",
    "fund",
    "platform",
    "fleet",
    "robot",
    "drone",
    "remote oper",
    "moderniz",
    "upgrade",
    "pilot program",
)

# Text that looks like company bio / article dump, not a pain point
_DESCRIPTION_LIKE_RE = re.compile(
    r"\b(is a leading|founded in|headquartered|company overview|about us|"
    r"forbes|bloomberg|reuters|future outlook|continue reading|"
    r"translating |market analysis|in this article)\b",
    re.IGNORECASE,
)

_NEWS_CATEGORIES: frozenset[str] = frozenset(
    {
        "company_news",
        "investment",
        "automation_investment",
        "technology_announcement",
        "expansion",
        "partnership",
        "funding",
        "safety_incident",
        "industry_article",
        "press_release",
        "hiring",
        "company_overview",
    }
)

_CATEGORY_ALIASES: dict[str, str] = {
    "press_release": "company_news",
    "tech_announcement": "technology_announcement",
    "technology": "technology_announcement",
    "funding_round": "funding",
    "investment": "investment",
    "automation": "automation_investment",
    "safety": "safety_incident",
    "industry": "industry_article",
    "partner": "partnership",
}


def clean_text(value: Any, *, max_len: int = _MAX_FIELD_LEN) -> str:
    """Strip markdown-ish noise and collapse whitespace."""
    if value is None:
        return ""
    text = str(value)
    # Drop markdown headings and bold markers lightly
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > max_len:
        # Prefer first sentence-ish chunk
        cut = text[:max_len]
        for sep in (". ", "; ", " — ", " - "):
            idx = cut.rfind(sep)
            if idx >= 60:
                cut = cut[: idx + 1]
                break
        text = cut.rstrip(" ,;") + ("…" if len(str(value)) > max_len else "")
    return text


def has_markdown_noise(text: str) -> bool:
    if not text:
        return False
    return bool(_MARKDOWN_RE.search(text))


def looks_like_description_bio(text: str) -> bool:
    """True when text reads like a company bio rather than a pain/buying label."""
    if not text:
        return False
    return bool(_DESCRIPTION_LIKE_RE.search(text))


def looks_like_article_dump(text: str) -> bool:
    if not text:
        return False
    if len(text) > _MAX_FIELD_LEN:
        return True
    if has_markdown_noise(text):
        return True
    if text.count(". ") >= 4 and len(text) > 180:
        return True
    return False


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(k in lower for k in keywords)


def _normalize_category(raw: Any, *, default: str = "company_news") -> str:
    if not raw:
        return default
    cat = str(raw).strip().lower().replace(" ", "_")
    cat = _CATEGORY_ALIASES.get(cat, cat)
    if cat in _NEWS_CATEGORIES:
        return cat
    # Keyword map from free text
    if "automat" in cat or "autonomous" in cat:
        return "automation_investment"
    if "fund" in cat or "series" in cat:
        return "funding"
    if "invest" in cat:
        return "investment"
    if "partner" in cat or "alliance" in cat:
        return "partnership"
    if "expand" in cat or "growth" in cat:
        return "expansion"
    if "safety" in cat or "incident" in cat:
        return "safety_incident"
    if "tech" in cat or "digital" in cat or "ai" in cat:
        return "technology_announcement"
    if "industry" in cat or "report" in cat:
        return "industry_article"
    if "hir" in cat or "job" in cat or "career" in cat:
        return "hiring"
    return default


def classify_news_category(
    *,
    title: str = "",
    summary: str = "",
    signal_category: str = "",
) -> str:
    """Map free text + collector category into a news taxonomy label."""
    if signal_category:
        mapped = _normalize_category(signal_category)
        if mapped != "company_news" or signal_category in _NEWS_CATEGORIES:
            # Prefer specific collector categories
            if signal_category in (
                "automation_investment",
                "technology_announcement",
                "safety_incident",
                "expansion",
                "partnership",
                "hiring",
                "industry_article",
                "funding",
            ):
                return signal_category if signal_category in _NEWS_CATEGORIES else mapped

    blob = f"{title} {summary} {signal_category}".lower()
    if any(k in blob for k in ("fund", "series a", "series b", "raised $", "capital")):
        return "funding"
    if any(k in blob for k in ("invest", "capex", "capital expenditure")):
        return "investment"
    if any(k in blob for k in ("autonomous", "automation", "robot", "drone fleet")):
        return "automation_investment"
    if any(k in blob for k in ("digital transform", "ai platform", "technology", "software")):
        return "technology_announcement"
    if any(k in blob for k in ("expand", "new mine", "new project", "market entry")):
        return "expansion"
    if any(k in blob for k in ("partner", "alliance", "joint venture", "collaboration")):
        return "partnership"
    if any(k in blob for k in ("safety", "fatality", "incident", "accident")):
        return "safety_incident"
    if any(k in blob for k in ("industry", "report", "analysis", "outlook")):
        return "industry_article"
    if signal_category == "press_release":
        return "company_news"
    return _normalize_category(signal_category, default="company_news")


def normalize_company_overview(
    raw: dict[str, Any] | None,
    *,
    company_name: str,
    domain: str,
    findings: dict[str, Any],
    signals: list[ResearchSignal],
) -> dict[str, Any]:
    """Build a clean company_overview block — never multi-article mashups."""
    raw = raw if isinstance(raw, dict) else {}

    def _field(*keys: str, max_len: int = _MAX_FIELD_LEN) -> str | None:
        for k in keys:
            v = raw.get(k)
            if v is None:
                v = findings.get(k)
            if v is None:
                continue
            cleaned = clean_text(v, max_len=max_len)
            if cleaned and not looks_like_article_dump(cleaned) and not has_markdown_noise(
                cleaned
            ):
                return cleaned
            if cleaned and len(cleaned) <= 120 and not has_markdown_noise(cleaned):
                return cleaned
        return None

    description = _field("description", max_len=280)
    if description and (
        looks_like_article_dump(description) or has_markdown_noise(description)
    ):
        description = None
    if not description:
        # Prefer a single company_overview / official-sounding signal
        for s in signals:
            if s.category == "company_overview" and s.summary:
                description = clean_text(s.summary.split(". ")[0], max_len=220)
                if description and not has_markdown_noise(description):
                    break
                description = None
        if not description:
            for s in signals:
                if s.summary:
                    # First sentence only from the strongest short snippet
                    description = clean_text(s.summary.split(". ")[0], max_len=200)
                    if description and not has_markdown_noise(description):
                        break
                    description = None
        if not description:
            description = (
                f"{company_name or domain} — public research signals collected; "
                "detailed overview not confidently extracted."
            )

    size_loc = _field("size_location", "location", max_len=120)
    employees = raw.get("employee_count")
    if employees is None:
        employees = findings.get("employee_count")

    return {
        "description": description,
        "industry": _field("industry", max_len=80),
        "business_model": _field("business_model", max_len=200),
        "major_operations": _field("major_operations", max_len=220),
        "geographic_presence": _field("geographic_presence", "location", max_len=160),
        "size_location": size_loc
        or (
            f"{employees} employees, {size_loc}" if employees and size_loc else size_loc
        ),
        "employee_count": employees,
        "location": _field("location", max_len=120),
    }


def normalize_pain_points(
    raw_items: Any,
    signals: list[ResearchSignal],
) -> list[dict[str, str]]:
    """Keep only short, operational, FlytBase-relevant pain points."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def _try_add(pain: str, evidence: str, url: str) -> None:
        pain_c = clean_text(pain, max_len=160)
        evid_c = clean_text(evidence, max_len=_MAX_EVIDENCE_LEN)
        if not pain_c or not url:
            return
        if looks_like_article_dump(pain_c) or has_markdown_noise(pain_c):
            return
        if looks_like_description_bio(pain_c):
            return
        if looks_like_article_dump(evid_c):
            evid_c = clean_text(evid_c.split(". ")[0], max_len=160)
        # Prefer operational themes; allow short pains with a source even if weak
        blob = f"{pain_c} {evid_c}".lower()
        if not _contains_any(blob, _PAIN_KEYWORDS) and len(pain_c) > 100:
            return
        key = pain_c.lower()[:80]
        if key in seen:
            return
        seen.add(key)
        out.append(
            {
                "pain_point": pain_c,
                "evidence": evid_c or pain_c,
                "source_url": url,
            }
        )

    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, str):
                continue  # bare strings are usually dumps
            if isinstance(item, dict):
                _try_add(
                    str(item.get("pain_point") or item.get("title") or ""),
                    str(item.get("evidence") or item.get("summary") or ""),
                    str(item.get("source_url") or item.get("url") or ""),
                )

    # Evidence-based fill if empty — map operational themes from signal text
    if not out:
        for s in signals:
            if not s.url:
                continue
            blob = f"{s.title} {s.summary}".lower()
            if not _contains_any(blob, _PAIN_KEYWORDS):
                continue
            # Prefer a short operational label from title
            pain = clean_text(s.title, max_len=140)
            if looks_like_description_bio(pain) or looks_like_article_dump(pain):
                # Derive a compact theme label from keywords present
                if "inspect" in blob:
                    pain = "Manual inspection burden"
                elif "safety" in blob or "risk" in blob:
                    pain = "Safety exposure in field operations"
                elif "remote" in blob or "monitor" in blob:
                    pain = "Remote monitoring and visibility gaps"
                elif "scale" in blob or "fleet" in blob:
                    pain = "Fleet scaling and coordination challenges"
                elif "automat" in blob:
                    pain = "Limited operational automation"
                else:
                    pain = clean_text(s.title.split("—")[0].split("-")[0], max_len=100)
            evid = clean_text((s.summary or s.title).split(". ")[0], max_len=160)
            _try_add(pain, evid, s.url)
            if len(out) >= 5:
                break

    return out[:6]


def normalize_buying_signals(
    raw_items: Any,
    signals: list[ResearchSignal],
) -> list[dict[str, str]]:
    """Keep short buying-intent signals only."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def _try_add(signal: str, evidence: str, url: str) -> None:
        sig_c = clean_text(signal, max_len=160)
        evid_c = clean_text(evidence, max_len=_MAX_EVIDENCE_LEN)
        if not sig_c or not url:
            return
        if looks_like_article_dump(sig_c) or has_markdown_noise(sig_c):
            return
        if looks_like_description_bio(sig_c):
            return
        if looks_like_article_dump(evid_c):
            evid_c = clean_text(evid_c.split(". ")[0], max_len=160)
        blob = f"{sig_c} {evid_c}".lower()
        if not _contains_any(blob, _BUYING_KEYWORDS) and len(sig_c) > 90:
            return
        key = sig_c.lower()[:80]
        if key in seen:
            return
        seen.add(key)
        out.append(
            {
                "signal": sig_c,
                "evidence": evid_c or sig_c,
                "source_url": url,
            }
        )

    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, str):
                continue
            if isinstance(item, dict):
                _try_add(
                    str(item.get("signal") or item.get("title") or ""),
                    str(item.get("evidence") or item.get("summary") or ""),
                    str(item.get("source_url") or item.get("url") or ""),
                )

    if not out:
        for s in signals:
            if not s.url:
                continue
            blob = f"{s.title} {s.summary}".lower()
            if not _contains_any(blob, _BUYING_KEYWORDS):
                # Category alone can imply buying intent
                if s.category not in (
                    "automation_investment",
                    "technology_announcement",
                    "expansion",
                    "partnership",
                    "funding",
                    "hiring",
                ):
                    continue
            sig = clean_text(s.title, max_len=140)
            if looks_like_description_bio(sig):
                if "fund" in blob or "raised" in blob or "series" in blob:
                    sig = "Recent funding activity"
                elif "automat" in blob or "autonomous" in blob:
                    sig = "Automation / autonomous operations investment"
                elif "expand" in blob:
                    sig = "Operational expansion"
                elif "partner" in blob:
                    sig = "Strategic partnership activity"
                elif "integrat" in blob or "platform" in blob:
                    sig = "Platform integration / technology adoption"
                else:
                    sig = clean_text(s.title.split("—")[0], max_len=100)
            evid = clean_text((s.summary or s.title).split(". ")[0], max_len=160)
            _try_add(sig, evid, s.url)
            if len(out) >= 5:
                break

    return out[:6]


def normalize_latest_news(
    raw_items: Any,
    signals: list[ResearchSignal],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(title: str, url: str, date: Any, summary: str, category: str) -> None:
        title_c = clean_text(title, max_len=_MAX_TITLE_LEN)
        summary_c = clean_text(summary, max_len=200)
        if not title_c or not url:
            return
        if looks_like_article_dump(summary_c) and len(summary_c) > 200:
            summary_c = clean_text(summary_c.split(". ")[0], max_len=160)
        key = url.lower().rstrip("/")
        if key in seen:
            return
        seen.add(key)
        out.append(
            {
                "title": title_c,
                "url": url,
                "date": date if date not in ("", None) else None,
                "summary": summary_c or title_c,
                "category": classify_news_category(
                    title=title_c,
                    summary=summary_c,
                    signal_category=category,
                ),
            }
        )

    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            _add(
                str(item.get("title") or ""),
                str(item.get("url") or item.get("source_url") or ""),
                item.get("date"),
                str(item.get("summary") or ""),
                str(item.get("category") or "company_news"),
            )

    if not out:
        for s in signals:
            if not s.url:
                continue
            _add(s.title, s.url, s.date, s.summary or s.title, s.category)
            if len(out) >= 8:
                break

    return out[:10]


def normalize_recent_signals(
    raw_items: Any,
    signals: list[ResearchSignal],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(item: dict[str, Any]) -> None:
        url = str(item.get("url") or item.get("source_url") or "")
        title = clean_text(item.get("title") or "", max_len=_MAX_TITLE_LEN)
        summary = clean_text(item.get("summary") or "", max_len=200)
        if not url or not title:
            return
        key = url.lower().rstrip("/")
        if key in seen:
            return
        seen.add(key)
        cat = classify_news_category(
            title=title,
            summary=summary,
            signal_category=str(item.get("category") or ""),
        )
        out.append(
            {
                "title": title,
                "url": url,
                "date": item.get("date"),
                "summary": summary or title,
                "category": cat,
                "source_type": item.get("source_type") or "public_web",
            }
        )

    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, dict):
                _add(item)

    if not out:
        for s in signals:
            _add(
                {
                    "title": s.title,
                    "url": s.url,
                    "date": s.date,
                    "summary": s.summary,
                    "category": s.category,
                    "source_type": s.source_type,
                }
            )
            if len(out) >= 15:
                break

    return out[:15]


def validate_synthesis_quality(findings: dict[str, Any]) -> list[str]:
    """Return list of quality problems; empty means acceptable."""
    problems: list[str] = []

    overview = findings.get("company_overview") or {}
    if isinstance(overview, dict):
        desc = str(overview.get("description") or findings.get("description") or "")
        if has_markdown_noise(desc):
            problems.append("overview_markdown")
        if looks_like_article_dump(desc) and len(desc) > 280:
            problems.append("overview_article_dump")
        # Multiple article mashup heuristic: many sentence breaks + length
        if desc.count(". ") >= 5 and len(desc) > 320:
            problems.append("overview_multi_source_mashup")
    else:
        problems.append("overview_missing")

    for p in findings.get("operational_pain_points") or []:
        if isinstance(p, str):
            problems.append("pain_unstructured")
            break
        if isinstance(p, dict):
            text = str(p.get("pain_point") or "")
            if has_markdown_noise(text) or looks_like_article_dump(text):
                problems.append("pain_dump")
                break
            if _DESCRIPTION_LIKE_RE.search(text):
                problems.append("pain_looks_like_description")
                break

    for b in findings.get("buying_signals") or []:
        if isinstance(b, str):
            problems.append("buying_unstructured")
            break
        if isinstance(b, dict):
            text = str(b.get("signal") or "")
            if has_markdown_noise(text) or looks_like_article_dump(text):
                problems.append("buying_dump")
                break

    return problems


def evidence_based_extraction(
    *,
    company_name: str,
    domain: str,
    collected_signals: list[ResearchSignal],
    inbound_context: str = "",
    base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a clean structured report strictly from collected signals."""
    base = dict(base or {})
    overview = normalize_company_overview(
        base.get("company_overview") if isinstance(base.get("company_overview"), dict) else base,
        company_name=company_name,
        domain=domain,
        findings=base,
        signals=collected_signals,
    )
    pains = normalize_pain_points(base.get("operational_pain_points"), collected_signals)
    buying = normalize_buying_signals(base.get("buying_signals"), collected_signals)
    news = normalize_latest_news(base.get("latest_news"), collected_signals)
    recent = normalize_recent_signals(base.get("recent_signals"), collected_signals)

    sources = []
    seen_src: set[str] = set()
    for s in collected_signals:
        if s.url and s.url not in seen_src:
            seen_src.add(s.url)
            sources.append(s.url)

    evidence = [
        {
            "claim": clean_text(s.summary or s.title, max_len=200),
            "source_url": s.url,
        }
        for s in collected_signals
        if s.url and (s.summary or s.title)
    ][:20]

    why_now = clean_text(
        base.get("why_now")
        or (
            f"Inbound interest and {len(collected_signals)} public signals indicate "
            f"automation / operations themes for {company_name or domain}."
            if inbound_context.strip()
            else f"Public signals indicate automation and operational activity for "
            f"{company_name or domain}."
        ),
        max_len=280,
    )

    sales = clean_text(
        base.get("recommended_sales_angle")
        or (
            "Lead with safety and inspection automation — position FlytBase as the "
            "drone fleet layer for site monitoring and remote operations."
        ),
        max_len=280,
    )

    next_action = clean_text(
        base.get("next_action")
        or base.get("recommended_next_action")
        or "Schedule a discovery call focused on inspection automation and remote ops.",
        max_len=200,
    )

    fit = clean_text(
        base.get("flytbase_fit")
        or (
            "Autonomous inspection missions, remote fleet orchestration, and "
            "real-time site monitoring for multi-site operations."
        ),
        max_len=240,
    )

    return {
        **base,
        "company_name": company_name or base.get("company_name") or "",
        "domain": domain or base.get("domain") or "",
        "description": overview["description"],
        "industry": overview.get("industry"),
        "business_model": overview.get("business_model"),
        "major_operations": overview.get("major_operations"),
        "geographic_presence": overview.get("geographic_presence"),
        "employee_count": overview.get("employee_count"),
        "location": overview.get("location"),
        "company_overview": overview,
        "latest_news": news,
        "operational_pain_points": pains,
        "buying_signals": buying,
        "pain_points": [p["pain_point"] for p in pains][:5],
        "recent_signals": recent,
        "business_signals": [
            {
                "signal": clean_text(s.summary or s.title, max_len=160),
                "category": classify_news_category(
                    title=s.title, summary=s.summary or "", signal_category=s.category
                ),
                "source_url": s.url,
                "url": s.url,
                "summary": clean_text(s.summary or "", max_len=180),
                "date": s.date,
                "source_type": s.source_type,
            }
            for s in collected_signals
            if s.url
        ][:12],
        "technology_signals": [
            clean_text(s.title, max_len=120)
            for s in collected_signals
            if s.category
            in ("technology_announcement", "automation_investment", "tech_announcement")
        ][:8],
        "why_now": why_now,
        "recommended_sales_angle": sales,
        "flytbase_fit": fit,
        "flytbase_relevance": clean_text(
            base.get("flytbase_relevance")
            or "High when automation, inspection, or remote operations signals are present.",
            max_len=220,
        ),
        "recommended_next_action": next_action,
        "next_action": next_action,
        "sources": sources,
        "evidence": evidence,
        "confidence_score": min(
            int(base.get("confidence_score") or 0)
            or min(max(len(collected_signals) * 4, 25), 70),
            100,
        ),
    }


def normalize_and_validate_findings(
    findings: dict[str, Any],
    *,
    company_name: str,
    domain: str,
    collected_signals: list[ResearchSignal],
    inbound_context: str = "",
) -> dict[str, Any]:
    """Normalize synthesis output; if still invalid, rebuild from evidence."""
    # First pass: soft normalize
    overview = normalize_company_overview(
        findings.get("company_overview")
        if isinstance(findings.get("company_overview"), dict)
        else findings,
        company_name=company_name,
        domain=domain,
        findings=findings,
        signals=collected_signals,
    )
    findings = {
        **findings,
        "description": overview["description"],
        "industry": overview.get("industry") or findings.get("industry"),
        "business_model": overview.get("business_model") or findings.get("business_model"),
        "major_operations": overview.get("major_operations")
        or findings.get("major_operations"),
        "geographic_presence": overview.get("geographic_presence")
        or findings.get("geographic_presence"),
        "location": overview.get("location") or findings.get("location"),
        "employee_count": overview.get("employee_count")
        or findings.get("employee_count"),
        "company_overview": overview,
        "operational_pain_points": normalize_pain_points(
            findings.get("operational_pain_points"), collected_signals
        ),
        "buying_signals": normalize_buying_signals(
            findings.get("buying_signals"), collected_signals
        ),
        "latest_news": normalize_latest_news(
            findings.get("latest_news"), collected_signals
        ),
        "recent_signals": normalize_recent_signals(
            findings.get("recent_signals"), collected_signals
        ),
        "pain_points": [],
        "why_now": clean_text(findings.get("why_now") or "", max_len=280),
        "recommended_sales_angle": clean_text(
            findings.get("recommended_sales_angle") or "", max_len=280
        ),
        "flytbase_fit": clean_text(findings.get("flytbase_fit") or "", max_len=240),
        "next_action": clean_text(
            findings.get("next_action")
            or findings.get("recommended_next_action")
            or "",
            max_len=200,
        ),
    }
    findings["pain_points"] = [
        p["pain_point"] for p in findings["operational_pain_points"]
    ][:5]
    if not findings.get("next_action") and not findings.get("recommended_next_action"):
        findings["next_action"] = (
            "Schedule a discovery call focused on inspection automation "
            "and remote operations."
        )
        findings["recommended_next_action"] = findings["next_action"]
    else:
        findings["recommended_next_action"] = findings.get("next_action") or findings.get(
            "recommended_next_action", ""
        )
        findings["next_action"] = findings["recommended_next_action"]

    problems = validate_synthesis_quality(findings)
    # Also rebuild if pains/buying empty despite having signals
    if not problems and collected_signals:
        if not findings.get("operational_pain_points") and not findings.get(
            "buying_signals"
        ):
            problems = ["empty_actionable_fields"]

    if problems:
        logger.info(
            "[SYNTHESIS NORMALIZE] invalid=%s company=%s — evidence-based rebuild",
            ",".join(problems),
            company_name,
        )
        return evidence_based_extraction(
            company_name=company_name,
            domain=domain,
            collected_signals=collected_signals,
            inbound_context=inbound_context,
            base=findings,
        )

    # Ensure evidence/sources present when signals exist
    if collected_signals and not findings.get("evidence"):
        findings["evidence"] = [
            {
                "claim": clean_text(s.summary or s.title, max_len=200),
                "source_url": s.url,
            }
            for s in collected_signals
            if s.url
        ][:20]
    if collected_signals and not findings.get("sources"):
        findings["sources"] = [s.url for s in collected_signals if s.url]

    logger.info(
        "[SYNTHESIS NORMALIZE] ok company=%s pains=%s buying=%s news=%s",
        company_name,
        len(findings.get("operational_pain_points") or []),
        len(findings.get("buying_signals") or []),
        len(findings.get("latest_news") or []),
    )
    return findings

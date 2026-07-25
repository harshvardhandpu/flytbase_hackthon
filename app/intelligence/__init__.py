"""Reusable, structured intelligence assembled from ScoutOS research data."""

from app.intelligence.account_research import AccountResearchIntelligence
from app.intelligence.company_resolver import CompanyResolver, extract_domain
from app.intelligence.outreach_brief import CompanyIntelligenceBriefBuilder
from app.intelligence.signal_collector import ResearchSignal, SignalCollector

__all__ = [
    "CompanyIntelligenceBriefBuilder",
    "AccountResearchIntelligence",
    "CompanyResolver",
    "extract_domain",
    "SignalCollector",
    "ResearchSignal",
]

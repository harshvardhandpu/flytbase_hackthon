"""Reusable, structured intelligence assembled from ScoutOS research data."""

from app.intelligence.account_research import AccountResearchIntelligence
from app.intelligence.company_resolver import CompanyResolver, extract_domain
from app.intelligence.outreach_brief import CompanyIntelligenceBriefBuilder

__all__ = [
    "CompanyIntelligenceBriefBuilder",
    "AccountResearchIntelligence",
    "CompanyResolver",
    "extract_domain",
]

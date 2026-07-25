"""Company Resolver — extracts company intelligence from an email address.

Given an email like ``john@riotinto.com``, the resolver:

1.  Extracts the domain (``riotinto.com``)
2.  Resolves the domain to a company name and profile
3.  Returns structured company data for downstream enrichment

The resolver uses a built-in mapping for well-known companies and falls
back to domain-based heuristics for unknown domains.  This avoids an
external API dependency during the hackathon demo; a real
implementation would use Clearbit, Hunter.io, or similar.
"""

from __future__ import annotations

import re
from typing import Any

# ── Well-known company domain mappings ─────────────────────────────────
# Extensible mapping used for demo / hackathon scenarios.
_KNOWN_COMPANIES: dict[str, dict[str, Any]] = {
    "riotinto.com": {
        "company_name": "Rio Tinto",
        "domain": "riotinto.com",
        "industry": "Mining",
        "employees": 50000,
        "location": "London, UK / Melbourne, Australia",
        "website": "https://www.riotinto.com",
    },
    "skygrid.com": {
        "company_name": "SkyGrid",
        "domain": "skygrid.com",
        "industry": "Drone Services",
        "employees": 200,
        "location": "San Francisco, US",
        "website": "https://www.skygrid.com",
    },
    "flytbase.com": {
        "company_name": "FlytBase",
        "domain": "flytbase.com",
        "industry": "Drone Technology",
        "employees": 150,
        "location": "San Francisco, US",
        "website": "https://www.flytbase.com",
    },
    "bhp.com": {
        "company_name": "BHP",
        "domain": "bhp.com",
        "industry": "Mining",
        "employees": 40000,
        "location": "Melbourne, Australia",
        "website": "https://www.bhp.com",
    },
    "vale.com": {
        "company_name": "Vale",
        "domain": "vale.com",
        "industry": "Mining",
        "employees": 60000,
        "location": "Rio de Janeiro, Brazil",
        "website": "https://www.vale.com",
    },
    "angloamerican.com": {
        "company_name": "Anglo American",
        "domain": "angloamerican.com",
        "industry": "Mining",
        "employees": 45000,
        "location": "London, UK",
        "website": "https://www.angloamerican.com",
    },
    "newmont.com": {
        "company_name": "Newmont",
        "domain": "newmont.com",
        "industry": "Mining",
        "employees": 12000,
        "location": "Denver, US",
        "website": "https://www.newmont.com",
    },
}


def extract_domain(email: str) -> str:
    """Extract the domain portion from an email address.

    >>> extract_domain("john@riotinto.com")
    'riotinto.com'
    >>> extract_domain("user@sub.example.co.uk")
    'sub.example.co.uk'
    """
    match = re.search(r"@([\w.-]+)", email.strip().lower())
    if not match:
        raise ValueError(f"Could not extract domain from email: {email!r}")
    return match.group(1)


def domain_to_company_name(domain: str) -> str:
    """Derive a human-readable company name from a domain.

    ``riotinto.com`` → ``Rio Tinto``  (known)
    ``acmecorp.io``  → ``Acmecorp``   (derived)
    """
    # Check known mapping first
    known = _KNOWN_COMPANIES.get(domain)
    if known:
        return known["company_name"]

    # Derive from domain: acmecorp.com → Acmecorp
    name = domain.rsplit(".", 1)[0]  # strip TLD
    # Handle subdomains: sub.example.com → Example
    parts = name.rsplit(".", 1)
    name = parts[-1] if len(parts) > 1 else parts[0]
    # Capitalize
    return name.capitalize()


class CompanyResolver:
    """Resolve structured company intelligence from an email address.

    The resolver is stateless and safe to reuse across requests.
    For the hackathon demo it uses a built-in mapping.  A production
    version would call an external API (Clearbit, Hunter.io, etc.).
    """

    def resolve(self, email: str) -> dict[str, Any]:
        """Resolve an email address to a company profile.

        Args:
            email: Sender email address (e.g. ``john@riotinto.com``).

        Returns:
            Dict with keys: ``company_name``, ``domain``, ``industry``,
            ``employees``, ``location``, ``website``, ``source``.

        Raises:
            ValueError: If the email has no parsable domain.
        """
        domain = extract_domain(email)

        known = _KNOWN_COMPANIES.get(domain)
        if known:
            return {**known, "source": "known_mapping"}

        # Fallback: derive from domain
        return {
            "company_name": domain_to_company_name(domain),
            "domain": domain,
            "industry": None,
            "employees": None,
            "location": None,
            "website": f"https://www.{domain}",
            "source": "domain_derived",
        }

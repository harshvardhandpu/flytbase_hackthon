"""Tests for the CompanyResolver service."""

from __future__ import annotations

import pytest

from app.intelligence.company_resolver import CompanyResolver, extract_domain


class TestExtractDomain:
    def test_extracts_domain_from_simple_email(self) -> None:
        assert extract_domain("john@riotinto.com") == "riotinto.com"

    def test_extracts_domain_with_subdomain(self) -> None:
        assert extract_domain("user@sub.example.co.uk") == "sub.example.co.uk"

    def test_handles_uppercase_email(self) -> None:
        assert extract_domain("USER@RIOTINTO.COM") == "riotinto.com"

    def test_handles_plus_addressing(self) -> None:
        assert extract_domain("john+test@riotinto.com") == "riotinto.com"

    def test_raises_on_missing_at(self) -> None:
        with pytest.raises(ValueError, match="Could not extract domain"):
            extract_domain("notanemail")


class TestCompanyResolver:
    def test_resolves_known_company(self) -> None:
        resolver = CompanyResolver()
        result = resolver.resolve("michael.anderson@riotinto.com")

        assert result["company_name"] == "Rio Tinto"
        assert result["domain"] == "riotinto.com"
        assert result["industry"] == "Mining"
        assert result["employees"] == 50000
        assert result["location"] == "London, UK / Melbourne, Australia"
        assert result["source"] == "known_mapping"

    def test_resolves_skygrid(self) -> None:
        resolver = CompanyResolver()
        result = resolver.resolve("contact@skygrid.com")

        assert result["company_name"] == "SkyGrid"
        assert result["domain"] == "skygrid.com"
        assert result["source"] == "known_mapping"

    def test_resolves_bhp(self) -> None:
        resolver = CompanyResolver()
        result = resolver.resolve("info@bhp.com")

        assert result["company_name"] == "BHP"
        assert result["industry"] == "Mining"
        assert result["source"] == "known_mapping"

    def test_resolves_unknown_domain(self) -> None:
        resolver = CompanyResolver()
        result = resolver.resolve("john@unknown-corp.io")

        assert result["domain"] == "unknown-corp.io"
        assert result["company_name"] == "Unknown-corp"
        assert result["industry"] is None
        assert result["employees"] is None
        assert result["source"] == "domain_derived"

    def test_resolves_and_capitalizes_domain(self) -> None:
        resolver = CompanyResolver()
        result = resolver.resolve("user@acmecorp.com")

        assert result["company_name"] == "Acmecorp"
        assert result["domain"] == "acmecorp.com"
        assert result["source"] == "domain_derived"

    def test_raises_on_invalid_email(self) -> None:
        resolver = CompanyResolver()
        with pytest.raises(ValueError, match="Could not extract domain"):
            resolver.resolve("not-an-email")

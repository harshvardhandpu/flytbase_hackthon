"""Tests for the OpenAI provider — URL normalisation and edge cases."""

from __future__ import annotations

from app.providers.openai import _normalize_openai_base_url


class TestNormalizeOpenaiBaseUrl:
    """``_normalize_openai_base_url()`` must strip trailing ``/v1`` before
    the provider appends ``/v1/chat/completions`` to avoid double-path
    bugs such as ``https://integrate.api.nvidia.com/v1/v1/chat/completions``.
    """

    # ── Standard NVIDIA base URL (no trailing /v1) ─────────────────────

    def test_nvidia_bare(self) -> None:
        """Bare NVIDIA URL should stay as-is."""
        result = _normalize_openai_base_url("https://integrate.api.nvidia.com")
        assert result == "https://integrate.api.nvidia.com"

    def test_nvidia_with_trailing_slash(self) -> None:
        """Trailing slash should be stripped."""
        result = _normalize_openai_base_url("https://integrate.api.nvidia.com/")
        assert result == "https://integrate.api.nvidia.com"

    # ── NVIDIA base URL with /v1 suffix (caused the 404 bug) ───────────

    def test_nvidia_with_v1(self) -> None:
        """``/v1`` suffix should be stripped — this was the original bug."""
        result = _normalize_openai_base_url("https://integrate.api.nvidia.com/v1")
        assert result == "https://integrate.api.nvidia.com"

    def test_nvidia_with_v1_trailing_slash(self) -> None:
        """``/v1/`` should be stripped."""
        result = _normalize_openai_base_url("https://integrate.api.nvidia.com/v1/")
        assert result == "https://integrate.api.nvidia.com"

    # ── Standard OpenAI base URL ───────────────────────────────────────

    def test_openai_bare(self) -> None:
        """Standard OpenAI URL without /v1 should be unchanged."""
        result = _normalize_openai_base_url("https://api.openai.com")
        assert result == "https://api.openai.com"

    def test_openai_with_trailing_slash(self) -> None:
        """Trailing slash should be stripped for OpenAI too."""
        result = _normalize_openai_base_url("https://api.openai.com/")
        assert result == "https://api.openai.com"

    # ── Custom / enterprise base URLs ──────────────────────────────────

    def test_custom_path_kept(self) -> None:
        """A path component like ``/api/v1`` should only strip the last
        ``/v1`` segment, preserving the rest of the path.

        ``https://proxy.example.com/api/v1`` → ``https://proxy.example.com/api``
        """
        result = _normalize_openai_base_url("https://proxy.example.com/api/v1")
        assert result == "https://proxy.example.com/api"

    def test_custom_path_no_v1_kept(self) -> None:
        """A custom path without `/v1` should be fully preserved."""
        result = _normalize_openai_base_url("https://proxy.example.com/custom/path")
        assert result == "https://proxy.example.com/custom/path"

    def test_v1_in_middle_kept(self) -> None:
        """Only a **trailing** ``/v1`` should be stripped — mid-path
        ``/v1/`` segments must be preserved."""
        result = _normalize_openai_base_url("https://proxy.example.com/v1/custom")
        assert result == "https://proxy.example.com/v1/custom"

    # ── Empty / edge inputs ────────────────────────────────────────────

    def test_empty_string(self) -> None:
        """Empty string should not crash."""
        result = _normalize_openai_base_url("")
        assert result == ""

    def test_only_v1(self) -> None:
        """A bare ``/v1`` should reduce to empty string."""
        result = _normalize_openai_base_url("/v1")
        assert result == ""

    def test_only_v1_trailing_slash(self) -> None:
        """A bare ``/v1/`` should reduce to empty string."""
        result = _normalize_openai_base_url("/v1/")
        assert result == ""

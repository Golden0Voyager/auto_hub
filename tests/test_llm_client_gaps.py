"""Coverage gap tests for auto_hub.llm.client — internal helper functions."""

from unittest.mock import MagicMock, patch

# Import the module directly to access private helpers
from auto_hub.llm import client as llm_client


class TestExtractRetryAfter:
    """_extract_retry_after() — edge cases for RateLimitError header parsing."""

    def test_no_response_object(self):
        """Exception without response attribute → None (defensive branch)."""
        from openai import RateLimitError

        resp = MagicMock(status_code=429, request=MagicMock(), headers={})
        exc = RateLimitError("test", response=resp, body=None)
        # Remove the response attribute to exercise the defensive guard
        with patch.object(exc, "response", None):
            result = llm_client._extract_retry_after(exc)
        assert result is None

    def test_headers_no_retry_after(self):
        """RateLimitError with headers but no retry-after key → None."""
        from openai import RateLimitError

        exc = RateLimitError("no retry header", response=MagicMock(headers={"x-request-id": "abc"}), body=None)
        result = llm_client._extract_retry_after(exc)
        assert result is None

    def test_retry_after_valid(self):
        """RateLimitError with valid retry-after header → float."""
        from openai import RateLimitError

        exc = RateLimitError("retry after 5s", response=MagicMock(headers={"retry-after": "5.0"}), body=None)
        result = llm_client._extract_retry_after(exc)
        assert result == 5.0

    def test_retry_after_invalid_float(self):
        """RateLimitError with non-numeric retry-after → None."""
        from openai import RateLimitError

        exc = RateLimitError("bad retry", response=MagicMock(headers={"retry-after": "abc"}), body=None)
        result = llm_client._extract_retry_after(exc)
        assert result is None

    def test_retry_after_via_ratelimit_header(self):
        """RateLimitError with x-ratelimit-reset-requests header."""
        from openai import RateLimitError

        exc = RateLimitError(
            "reset",
            response=MagicMock(headers={"x-ratelimit-reset-requests": "30.0"}),
            body=None,
        )
        result = llm_client._extract_retry_after(exc)
        assert result == 30.0


class TestBuildOpenAIKwargs:
    """_build_openai_kwargs() — proxy and async_client edge cases."""

    def test_no_proxy(self, monkeypatch):
        """Without proxy env var, http_client is not set."""
        monkeypatch.delenv("PROXY", raising=False)
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.delenv("HTTP_PROXY", raising=False)

        config = MagicMock()
        config.api_key = "sk-test"
        config.base_url = "https://test.example.com/v1"

        kwargs = llm_client._build_openai_kwargs(config, async_client=False)
        assert kwargs["api_key"] == "sk-test"
        assert kwargs["base_url"] == "https://test.example.com/v1"
        assert "http_client" not in kwargs

    def test_with_proxy_sync(self, monkeypatch):
        """With PROXY env var, http_client is set with sync httpx.Client."""
        monkeypatch.setenv("PROXY", "http://proxy:8080")
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.delenv("HTTP_PROXY", raising=False)

        config = MagicMock()
        config.api_key = "sk-test"
        config.base_url = "https://test.example.com/v1"

        kwargs = llm_client._build_openai_kwargs(config, async_client=False)
        assert "http_client" in kwargs
        from httpx import Client
        assert isinstance(kwargs["http_client"], Client)

    def test_with_proxy_async(self, monkeypatch):
        """With HTTPS_PROXY env var, http_client is set with async httpx.AsyncClient."""
        monkeypatch.delenv("PROXY", raising=False)
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy:8080")
        monkeypatch.delenv("HTTP_PROXY", raising=False)

        config = MagicMock()
        config.api_key = "sk-test"
        config.base_url = "https://test.example.com/v1"

        kwargs = llm_client._build_openai_kwargs(config, async_client=True)
        assert "http_client" in kwargs
        from httpx import AsyncClient
        assert isinstance(kwargs["http_client"], AsyncClient)

    def test_with_http_proxy(self, monkeypatch):
        """Fallback to HTTP_PROXY when PROXY/HTTPS_PROXY are not set."""
        monkeypatch.delenv("PROXY", raising=False)
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.setenv("HTTP_PROXY", "http://proxy:3128")

        config = MagicMock()
        config.api_key = "sk-test"
        config.base_url = "https://test.example.com/v1"

        kwargs = llm_client._build_openai_kwargs(config, async_client=True)
        assert "http_client" in kwargs


class TestBuildKwargs:
    """_build_kwargs() — optional parameter forwarding."""

    def test_minimal(self):
        """Only model and messages — no extras."""
        kwargs = llm_client._build_kwargs("gpt-4", [{"role": "user", "content": "hi"}])
        assert kwargs["model"] == "gpt-4"
        assert kwargs["messages"] == [{"role": "user", "content": "hi"}]
        assert "temperature" not in kwargs
        assert "max_tokens" not in kwargs
        assert "response_format" not in kwargs

    def test_with_temperature(self):
        """temperature is included when not None."""
        kwargs = llm_client._build_kwargs(
            "gpt-4", [{"role": "user", "content": "hi"}], temperature=0.5
        )
        assert kwargs["temperature"] == 0.5

    def test_with_max_tokens(self):
        """max_tokens is included when not None."""
        kwargs = llm_client._build_kwargs(
            "gpt-4", [{"role": "user", "content": "hi"}], max_tokens=100
        )
        assert kwargs["max_tokens"] == 100

    def test_with_response_format(self):
        """response_format is included when not None."""
        fmt = {"type": "json_object"}
        kwargs = llm_client._build_kwargs(
            "gpt-4", [{"role": "user", "content": "hi"}], response_format=fmt
        )
        assert kwargs["response_format"] == fmt

    def test_with_all_options(self):
        """All optional params included together."""
        fmt = {"type": "json_object"}
        kwargs = llm_client._build_kwargs(
            "gpt-4", [{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=200,
            response_format=fmt,
        )
        assert kwargs["temperature"] == 0.7
        assert kwargs["max_tokens"] == 200
        assert kwargs["response_format"] == fmt


class TestProcessResponse:
    """_process_response() — edge cases for content extraction."""

    def test_normal_content(self):
        """Normal content string returned as-is."""
        mock = MagicMock()
        mock.choices[0].message.content = "hello"
        mock.usage = None
        stats = MagicMock()
        result = llm_client._process_response(mock, stats)
        assert result == "hello"

    def test_reasoning_content_fallback(self):
        """When content is empty, reasoning_content is used."""
        mock = MagicMock()
        mock.choices[0].message.content = ""
        mock.choices[0].message.reasoning = None
        mock.choices[0].message.reasoning_content = "thinking...\nfinal answer"
        mock.usage = None
        stats = MagicMock()
        result = llm_client._process_response(mock, stats)
        assert result == "final answer"

    def test_empty_result(self):
        """When both content and reasoning are empty, empty string returned."""
        mock = MagicMock()
        mock.choices[0].message.content = ""
        mock.choices[0].message.reasoning = None
        mock.choices[0].message.reasoning_content = None
        mock.usage = None
        stats = MagicMock()
        result = llm_client._process_response(mock, stats)
        assert result == ""

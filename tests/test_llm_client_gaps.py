"""Coverage gap tests for auto_hub.llm.client — internal helper functions and edge cases."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auto_hub.llm import AsyncLLMClient, LLMClient, reset_provider_chain
from auto_hub.llm import client as llm_client

# ---------------------------------------------------------------------------
# Helpers — set up a minimal provider chain
# ---------------------------------------------------------------------------

def _setup_chain_a(monkeypatch, extra_model: str = "model-a"):
    """Set env for a single provider A."""
    reset_provider_chain()
    monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
    monkeypatch.setenv("A_API_KEY", "key-a")
    monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")
    monkeypatch.setenv("A_MODEL", extra_model)


def _setup_chain_ab(monkeypatch):
    """Set env for two providers A,B."""
    reset_provider_chain()
    monkeypatch.setenv("AI_PROVIDER_CHAIN", "A,B")
    monkeypatch.setenv("A_API_KEY", "key-a")
    monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")
    monkeypatch.setenv("A_MODEL", "model-a")
    monkeypatch.setenv("B_API_KEY", "key-b")
    monkeypatch.setenv("B_BASE_URL", "https://b.example.com/v1")
    monkeypatch.setenv("B_MODEL", "model-b")


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_retry_after — RateLimitError header parsing edge cases
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# _build_openai_kwargs — proxy and async_client edge cases
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# _build_kwargs — optional parameter forwarding
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# _process_response — content extraction edge cases
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# _attempt_provider — edge cases for retry/rate-limit/no-model
# ═══════════════════════════════════════════════════════════════════════════════

class TestAttemptProvider:
    """_ChainRunner._attempt_provider — uncovered branches."""

    def test_no_model_skips_provider(self, monkeypatch):
        """Provider with empty model string is skipped (lines 138-139)."""
        reset_provider_chain()
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A,B")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")
        monkeypatch.setenv("A_MODEL", "")
        monkeypatch.setenv("B_API_KEY", "key-b")
        monkeypatch.setenv("B_BASE_URL", "https://b.example.com/v1")
        monkeypatch.setenv("B_MODEL", "model-b")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage = None

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create.return_value = mock_response
            client = LLMClient.from_env()
            result = client.chat([{"role": "user", "content": "hi"}])

        assert result == "ok"

    def test_rate_limit_last_retry_breaks(self, monkeypatch):
        """Rate limit on the ONLY attempt → break (line 158)."""
        from openai import RateLimitError

        _setup_chain_a(monkeypatch)

        def _always_rate_limit(**kwargs):
            raise RateLimitError("always", response=MagicMock(headers={}), body=None)

        with patch("auto_hub.llm.client.OpenAI") as mock_client, \
             patch("auto_hub.llm.client.time.sleep"):
            instance = mock_client.return_value
            instance.chat.completions.create = MagicMock(side_effect=_always_rate_limit)

            client = LLMClient.from_env(max_retries=1)
            with pytest.raises(RuntimeError, match="All LLM providers exhausted"):
                client.chat([{"role": "user", "content": "hi"}])

    def test_soft_error_retries_then_succeeds(self, monkeypatch):
        """Non-hard-fail error triggers retry with backoff (lines 168-171)."""
        _setup_chain_a(monkeypatch)

        mock_ok = MagicMock()
        mock_ok.choices = [MagicMock(message=MagicMock(content="retry-ok"))]
        mock_ok.usage = None

        with patch("auto_hub.llm.client.OpenAI") as mock_client, \
             patch("auto_hub.llm.client.time.sleep") as mock_sleep:
            instance = mock_client.return_value
            instance.chat.completions.create = MagicMock(
                side_effect=[Exception("timeout"), mock_ok]
            )

            client = LLMClient.from_env(max_retries=2)
            result = client.chat([{"role": "user", "content": "hi"}])

        assert result == "retry-ok"
        assert mock_sleep.called
        assert client.stats.failed_attempt_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# LLMClient — exhausted / no-chain / no-model edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestLLMClientEdgeCases:
    """LLMClient — edge cases for chat, chat_stream, response, response_stream."""

    def test_chat_all_exhausted(self, monkeypatch):
        """All providers fail → RuntimeError (line 300)."""
        _setup_chain_ab(monkeypatch)

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create = MagicMock(
                side_effect=Exception("always fail")
            )
            client = LLMClient.from_env()
            with pytest.raises(RuntimeError, match="All LLM providers exhausted"):
                client.chat([{"role": "user", "content": "hi"}])

    def test_chat_stream_no_chain(self, monkeypatch):
        """chat_stream with no providers configured (lines 337-338)."""
        reset_provider_chain()
        monkeypatch.delenv("AI_PROVIDER_CHAIN", raising=False)

        client = LLMClient.from_env()
        with pytest.raises(RuntimeError, match="No LLM providers"):
            list(client.chat_stream([{"role": "user", "content": "hi"}]))

    def test_chat_stream_provider_no_model(self, monkeypatch):
        """chat_stream with a provider that has no model (lines 345-346)."""
        reset_provider_chain()
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A,B")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")
        monkeypatch.setenv("A_MODEL", "")
        monkeypatch.setenv("B_API_KEY", "key-b")
        monkeypatch.setenv("B_BASE_URL", "https://b.example.com/v1")
        monkeypatch.setenv("B_MODEL", "model-b")

        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock(delta=MagicMock(content="ok"))]

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create.return_value = iter([mock_chunk])

            client = LLMClient.from_env()
            result = list(client.chat_stream([{"role": "user", "content": "hi"}]))

        assert result == ["ok"]

    def test_chat_stream_all_exhausted(self, monkeypatch):
        """chat_stream when all providers fail (line 361)."""
        _setup_chain_ab(monkeypatch)

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create = MagicMock(
                side_effect=Exception("stream fail")
            )
            client = LLMClient.from_env()
            with pytest.raises(RuntimeError, match="All providers exhausted"):
                list(client.chat_stream([{"role": "user", "content": "hi"}]))

    def test_chat_stream_running_loop_detection(self, monkeypatch):
        """chat_stream raises RuntimeError when called from event loop (lines 327, 331)."""
        import asyncio

        _setup_chain_a(monkeypatch)

        async def _call_it():
            gen = LLMClient.from_env().chat_stream([{"role": "user", "content": "hi"}])
            next(gen)

        with pytest.raises(RuntimeError, match="running event loop"):
            asyncio.run(_call_it())

    def test_response_no_chain(self, monkeypatch):
        """response with no providers configured (line 389)."""
        reset_provider_chain()
        monkeypatch.delenv("AI_PROVIDER_CHAIN", raising=False)

        client = LLMClient.from_env()
        with pytest.raises(RuntimeError, match="No LLM providers"):
            client.response("hi")

    def test_response_provider_no_model(self, monkeypatch):
        """response with provider that has no model (lines 399-400)."""
        _setup_chain_a(monkeypatch, extra_model="")

        mock_resp = MagicMock()
        mock_resp.output_text = "ok"

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.responses.create.return_value = mock_resp

            client = LLMClient.from_env()
            with pytest.raises(RuntimeError, match="failed on all compatible"):
                client.response("hi")

    def test_response_stream_no_chain(self, monkeypatch):
        """response_stream with no providers configured (line 443)."""
        reset_provider_chain()
        monkeypatch.delenv("AI_PROVIDER_CHAIN", raising=False)

        client = LLMClient.from_env()
        with pytest.raises(RuntimeError, match="No LLM providers"):
            list(client.response_stream("hi"))

    def test_response_stream_provider_no_model(self, monkeypatch):
        """response_stream with provider that has no model (lines 452-453)."""
        _setup_chain_a(monkeypatch, extra_model="")

        mock_event = MagicMock()
        mock_event.type = "response.output_text.delta"
        mock_event.delta = "ok"

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.responses.create.return_value = iter([mock_event])

            client = LLMClient.from_env()
            with pytest.raises(RuntimeError, match="failed on all compatible"):
                list(client.response_stream("hi"))

    def test_response_stream_strips_unmatched_attr(self, monkeypatch):
        """response_stream skips non-OpenAI providers (line 448)."""
        reset_provider_chain()
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "ANTHROPIC,OPENAI")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key-ant")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3")
        monkeypatch.setenv("OPENAI_API_KEY", "key-oa")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                    "PROXY", "proxy", "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
            monkeypatch.delenv(key, raising=False)
        reset_provider_chain()

        mock_event = MagicMock()
        mock_event.type = "response.output_text.delta"
        mock_event.delta = "from openai"

        with patch("auto_hub.llm.client.OpenAI") as mock_openai:
            mock_openai.return_value.responses.create.return_value = iter([mock_event])
            client = LLMClient.from_env()
            result = list(client.response_stream("hi"))

        assert result == ["from openai"]

    def test_response_stream_with_instructions_and_tools(self, monkeypatch):
        """response_stream passes instructions and tools kwargs (lines 460, 462)."""
        _setup_chain_a(monkeypatch)

        e1 = MagicMock()
        e1.type = "response.output_text.delta"
        e1.delta = "tool result"

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.responses.create.return_value = iter([e1])

            client = LLMClient.from_env()
            result = list(client.response_stream(
                "Search the web",
                instructions="Be helpful",
                tools=[{"type": "web_search_preview"}],
            ))

        assert result == ["tool result"]
        call_kwargs = instance.responses.create.call_args.kwargs
        assert call_kwargs["instructions"] == "Be helpful"
        assert call_kwargs["tools"] == [{"type": "web_search_preview"}]

    def test_response_stream_fallback(self, monkeypatch):
        """response_stream falls back on error then succeeds (lines 469-471)."""
        reset_provider_chain()
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A,B")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("B_API_KEY", "key-b")
        monkeypatch.setenv("B_BASE_URL", "https://b.example.com/v1")
        monkeypatch.setenv("B_MODEL", "model-b")

        e1 = MagicMock()
        e1.type = "response.output_text.delta"
        e1.delta = "fallback ok"

        call_order = []

        def mock_openai_factory(**kwargs):
            base_url = kwargs.get("base_url", "")
            call_order.append(base_url)
            instance = MagicMock()
            if "a.example" in base_url:
                instance.responses.create.side_effect = Exception("primary down")
            else:
                instance.responses.create.return_value = iter([e1])
            return instance

        with patch("auto_hub.llm.client.OpenAI", side_effect=mock_openai_factory):
            client = LLMClient.from_env()
            result = list(client.response_stream("Hello"))

        assert result == ["fallback ok"]
        assert call_order == ["https://a.example.com/v1", "https://b.example.com/v1"]

    def test_reset_cache(self, monkeypatch):
        """reset_cache clears client cache (lines 476-477)."""
        _setup_chain_a(monkeypatch)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage = None

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create.return_value = mock_response

            client = LLMClient.from_env()
            client.chat([{"role": "user", "content": "hi"}])
            assert len(client._client_cache) == 1

            client.reset_cache()
            assert len(client._client_cache) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# AsyncLLMClient — exhausted / no-chain / no-model edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestAsyncLLMClientEdgeCases:

    @pytest.mark.asyncio
    async def test_chat_all_exhausted(self, monkeypatch):
        _setup_chain_ab(monkeypatch)
        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create = AsyncMock(side_effect=Exception("fail"))
            client = AsyncLLMClient.from_env()
            with pytest.raises(RuntimeError, match="All LLM providers exhausted"):
                await client.chat([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_chat_stream_no_chain(self, monkeypatch):
        reset_provider_chain()
        monkeypatch.delenv("AI_PROVIDER_CHAIN", raising=False)
        client = AsyncLLMClient.from_env()
        with pytest.raises(RuntimeError, match="No LLM providers"):
            stream = client.chat_stream([{"role": "user", "content": "hi"}])
            async for _ in stream:
                pass

    @pytest.mark.asyncio
    async def test_chat_stream_provider_no_model(self, monkeypatch):
        _setup_chain_a(monkeypatch, extra_model="")
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock(delta=MagicMock(content="ok"))]

        class _MockIter:
            def __init__(self, items):
                self._items = iter(items)
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration from None

        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create = AsyncMock(
                return_value=_MockIter([mock_chunk])
            )
            client = AsyncLLMClient.from_env()
            with pytest.raises(RuntimeError, match="All providers exhausted"):
                stream = client.chat_stream([{"role": "user", "content": "hi"}])
                async for _ in stream:
                    pass

    @pytest.mark.asyncio
    async def test_chat_stream_all_exhausted(self, monkeypatch):
        _setup_chain_ab(monkeypatch)
        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create = AsyncMock(
                side_effect=Exception("fail")
            )
            client = AsyncLLMClient.from_env()
            with pytest.raises(RuntimeError, match="All providers exhausted"):
                stream = client.chat_stream([{"role": "user", "content": "hi"}])
                async for _ in stream:
                    pass

    @pytest.mark.asyncio
    async def test_response_no_chain(self, monkeypatch):
        reset_provider_chain()
        monkeypatch.delenv("AI_PROVIDER_CHAIN", raising=False)
        client = AsyncLLMClient.from_env()
        with pytest.raises(RuntimeError, match="No LLM providers"):
            await client.response("hi")

    @pytest.mark.asyncio
    async def test_response_provider_no_model(self, monkeypatch):
        _setup_chain_a(monkeypatch, extra_model="")
        client = AsyncLLMClient.from_env()
        with pytest.raises(RuntimeError, match="failed on all compatible"):
            await client.response("hi")

    @pytest.mark.asyncio
    async def test_response_all_exhausted(self, monkeypatch):
        _setup_chain_ab(monkeypatch)
        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            instance = mock_client.return_value
            instance.responses.create = AsyncMock(side_effect=Exception("fail"))
            client = AsyncLLMClient.from_env()
            with pytest.raises(RuntimeError, match="failed on all compatible"):
                await client.response("hi")

    @pytest.mark.asyncio
    async def test_response_skips_incompatible_providers(self, monkeypatch):
        """Async response skips providers without responses attr (line 644)."""
        reset_provider_chain()
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "ANTHROPIC,OPENAI")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key-ant")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3")
        monkeypatch.setenv("OPENAI_API_KEY", "key-oa")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                    "PROXY", "proxy", "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
            monkeypatch.delenv(key, raising=False)
        reset_provider_chain()

        mock_resp = MagicMock()
        mock_resp.output_text = "async ok"

        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(return_value=mock_resp)
            client = AsyncLLMClient.from_env()
            result = await client.response("hi")

        assert result == "async ok"

    @pytest.mark.asyncio
    async def test_response_with_instructions_and_tools(self, monkeypatch):
        """Async response passes instructions and tools (lines 652, 654)."""
        _setup_chain_a(monkeypatch)

        mock_resp = MagicMock()
        mock_resp.output_text = "tool result"

        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            instance = mock_client.return_value
            instance.responses.create = AsyncMock(return_value=mock_resp)
            client = AsyncLLMClient.from_env()
            result = await client.response(
                "Search the web",
                instructions="Be helpful",
                tools=[{"type": "web_search_preview"}],
            )

        assert result == "tool result"
        call_kwargs = instance.responses.create.call_args.kwargs
        assert call_kwargs["instructions"] == "Be helpful"
        assert call_kwargs["tools"] == [{"type": "web_search_preview"}]

    @pytest.mark.asyncio
    async def test_response_stream_no_chain(self, monkeypatch):
        reset_provider_chain()
        monkeypatch.delenv("AI_PROVIDER_CHAIN", raising=False)
        client = AsyncLLMClient.from_env()
        with pytest.raises(RuntimeError, match="No LLM providers"):
            stream = client.response_stream("hi")
            async for _ in stream:
                pass

    @pytest.mark.asyncio
    async def test_response_stream_provider_no_model(self, monkeypatch):
        _setup_chain_a(monkeypatch, extra_model="")
        client = AsyncLLMClient.from_env()
        with pytest.raises(RuntimeError, match="failed on all compatible"):
            stream = client.response_stream("hi")
            async for _ in stream:
                pass

    @pytest.mark.asyncio
    async def test_response_stream_all_exhausted(self, monkeypatch):
        _setup_chain_ab(monkeypatch)
        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            instance = mock_client.return_value
            instance.responses.create = AsyncMock(side_effect=Exception("fail"))
            client = AsyncLLMClient.from_env()
            with pytest.raises(RuntimeError, match="failed on all compatible"):
                stream = client.response_stream("hi")
                async for _ in stream:
                    pass

    @pytest.mark.asyncio
    async def test_response_stream_skips_incompatible_providers(self, monkeypatch):
        """Async response_stream skips providers without responses attr (line 685)."""
        reset_provider_chain()
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "ANTHROPIC,OPENAI")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key-ant")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3")
        monkeypatch.setenv("OPENAI_API_KEY", "key-oa")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                    "PROXY", "proxy", "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
            monkeypatch.delenv(key, raising=False)
        reset_provider_chain()

        e1 = MagicMock()
        e1.type = "response.output_text.delta"
        e1.delta = "async chunk"

        class _MockIter:
            def __init__(self, items):
                self._items = iter(items)
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration from None

        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            mock_client.return_value.responses.create = AsyncMock(
                return_value=_MockIter([e1])
            )
            client = AsyncLLMClient.from_env()
            result = []
            async for text in client.response_stream("hi"):
                result.append(text)

        assert result == ["async chunk"]

    @pytest.mark.asyncio
    async def test_response_stream_with_instructions_and_tools(self, monkeypatch):
        """Async response_stream passes instructions and tools (lines 697, 699)."""
        _setup_chain_a(monkeypatch)

        e1 = MagicMock()
        e1.type = "response.output_text.delta"
        e1.delta = "tool result"

        class _MockIter:
            def __init__(self, items):
                self._items = iter(items)
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration from None

        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            instance = mock_client.return_value
            instance.responses.create = AsyncMock(return_value=_MockIter([e1]))
            client = AsyncLLMClient.from_env()
            result = []
            async for text in client.response_stream(
                "Search the web",
                instructions="Be helpful",
                tools=[{"type": "web_search_preview"}],
            ):
                result.append(text)

        assert result == ["tool result"]
        call_kwargs = instance.responses.create.call_args.kwargs
        assert call_kwargs["instructions"] == "Be helpful"
        assert call_kwargs["tools"] == [{"type": "web_search_preview"}]

    @pytest.mark.asyncio
    async def test_reset_cache(self, monkeypatch):
        _setup_chain_a(monkeypatch)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
        mock_response.usage = None

        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_response)

            client = AsyncLLMClient.from_env()
            await client.chat([{"role": "user", "content": "hi"}])
            assert len(client._client_cache) == 1

            client.reset_cache()
            assert len(client._client_cache) == 0

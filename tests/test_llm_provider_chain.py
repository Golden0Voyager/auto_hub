"""Tests for auto_hub.llm — provider chain, JSON parsing, stats, and client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auto_hub.llm import (
    AnthropicClientWrapper,
    AsyncLLMClient,
    CallStats,
    GeminiClientWrapper,
    LLMClient,
    load_provider_chain,
    parse_llm_json,
    reset_provider_chain,
)

# ---------------------------------------------------------------------------
# Provider chain tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    reset_provider_chain()
    for name in ("A", "B", "C"):
        monkeypatch.delenv(f"{name}_API_KEY", raising=False)
        monkeypatch.delenv(f"{name}_MODEL", raising=False)
        monkeypatch.delenv(f"{name}_BASE_URL", raising=False)
    monkeypatch.delenv("AI_PROVIDER_CHAIN", raising=False)
    yield
    reset_provider_chain()


class TestProviderChain:
    def test_loads_chain_from_env(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "SENSENOVA,OPENAI")
        monkeypatch.setenv("SENSENOVA_API_KEY", "sk-ss")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oa")

        chain = load_provider_chain()

        assert len(chain) == 2
        assert chain[0].name == "SENSENOVA"
        assert chain[0].is_primary is True
        assert chain[1].name == "OPENAI"
        assert chain[1].is_primary is False

    def test_skips_providers_without_key(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A,B,C")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("C_API_KEY", "key-c")

        chain = load_provider_chain()

        assert len(chain) == 2
        assert chain[0].name == "A"
        assert chain[1].name == "C"

    def test_returns_empty_when_no_env(self):
        chain = load_provider_chain()
        assert chain == []

    def test_uses_default_base_urls(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "SENSENOVA")
        monkeypatch.setenv("SENSENOVA_API_KEY", "sk-ss")

        chain = load_provider_chain()

        assert len(chain) == 1
        assert chain[0].base_url == "https://api.sensenova.cn/compatible-mode/v2"


# ---------------------------------------------------------------------------
# JSON parsing tests
# ---------------------------------------------------------------------------


class TestParseLLMJson:
    def test_parses_direct_json(self):
        assert parse_llm_json('{"key": "value"}') == {"key": "value"}

    def test_parses_fenced_json(self):
        result = parse_llm_json('```json\n{"title": "test"}\n```')
        assert result == {"title": "test"}

    def test_parses_fenced_no_lang(self):
        result = parse_llm_json('```\n{"key": 1}\n```')
        assert result == {"key": 1}

    def test_parses_stripped_markdown(self):
        result = parse_llm_json('```\n{"key": 1}\n```')
        assert result == {"key": 1}

    def test_raises_on_invalid(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_llm_json("not json")

    def test_raises_on_empty(self):
        with pytest.raises(ValueError):
            parse_llm_json("")


# ---------------------------------------------------------------------------
# CallStats tests
# ---------------------------------------------------------------------------


class TestCallStats:
    def test_records_call(self):
        stats = CallStats()
        stats.record(100, 50)
        assert stats.call_count == 1
        assert stats.total_prompt_tokens == 100
        assert stats.total_completion_tokens == 50
        assert stats.total_tokens == 150

    def test_records_failure(self):
        stats = CallStats()
        stats.record_failure()
        assert stats.failed_attempt_count == 1

    def test_reset(self):
        stats = CallStats()
        stats.record(100, 50)
        stats.record_failure()
        stats.reset()
        assert stats.call_count == 0
        assert stats.failed_attempt_count == 0
        assert stats.total_tokens == 0

    def test_snapshot(self):
        stats = CallStats()
        stats.record(100, 50)
        snap = stats.snapshot()
        assert snap["call_count"] == 1
        assert snap["total_tokens"] == 150


# ---------------------------------------------------------------------------
# LLMClient tests
# ---------------------------------------------------------------------------


class TestLLMClient:
    def test_from_env_creates_client(self):
        client = LLMClient.from_env()
        assert client.max_retries == 2

    def test_raises_on_no_providers(self):
        client = LLMClient.from_env()
        with pytest.raises(RuntimeError, match="No LLM providers"):
            client.chat([{"role": "user", "content": "hi"}])

    def test_successful_call(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "hello"
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create.return_value = mock_response

            client = LLMClient.from_env()
            result = client.chat([{"role": "user", "content": "hi"}])

        assert result == "hello"
        assert client.stats.call_count == 1
        assert client.stats.total_prompt_tokens == 10

    def test_fallback_on_hard_fail(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A,B")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")
        monkeypatch.setenv("B_API_KEY", "key-b")
        monkeypatch.setenv("B_MODEL", "model-b")
        monkeypatch.setenv("B_BASE_URL", "https://b.example.com/v1")

        mock_ok = MagicMock()
        mock_ok_choice = MagicMock()
        mock_ok_choice.message.content = "fallback-ok"
        mock_ok.choices = [mock_ok_choice]
        mock_ok.usage = None

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create = MagicMock(
                side_effect=[Exception("invalid_api_key"), mock_ok]
            )

            client = LLMClient.from_env(max_retries=1)
            result = client.chat([{"role": "user", "content": "hi"}])

        assert result == "fallback-ok"
        assert client.stats.failed_attempt_count == 1

    def test_hard_fail_skips_retries(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A,B")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")
        monkeypatch.setenv("B_API_KEY", "key-b")
        monkeypatch.setenv("B_MODEL", "model-b")
        monkeypatch.setenv("B_BASE_URL", "https://b.example.com/v1")

        mock_ok = MagicMock()
        mock_ok_choice = MagicMock()
        mock_ok_choice.message.content = "ok"
        mock_ok.choices = [mock_ok_choice]
        mock_ok.usage = None

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create = MagicMock(
                side_effect=[Exception("authentication_error"), mock_ok]
            )

            client = LLMClient.from_env(max_retries=3)
            result = client.chat([{"role": "user", "content": "hi"}])

        assert result == "ok"
        assert instance.chat.completions.create.call_count == 2

    def test_reasoning_fallback(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_choice.message.reasoning = "thinking...\nfinal answer"
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create.return_value = mock_response

            client = LLMClient.from_env()
            result = client.chat([{"role": "user", "content": "hi"}])

        assert result == "final answer"

    def test_chat_json(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"key": "value"}'
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create.return_value = mock_response

            client = LLMClient.from_env()
            result = client.chat_json([{"role": "user", "content": "hi"}])

        assert result == {"key": "value"}

    def test_rate_limit_retry(self, monkeypatch):
        from openai import RateLimitError

        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")
        monkeypatch.setenv("A_RATE_LIMIT_DELAY_OVERRIDE", "0")  # not used; we'll patch sleep

        mock_ok = MagicMock()
        mock_ok_choice = MagicMock()
        mock_ok_choice.message.content = "after-retry"
        mock_ok.choices = [mock_ok_choice]
        mock_ok.usage = None

        rate_err = RateLimitError("rate limit", response=MagicMock(headers={}), body=None)

        with patch("auto_hub.llm.client.OpenAI") as mock_client, \
             patch("auto_hub.llm.client.time.sleep") as mock_sleep:
            instance = mock_client.return_value
            instance.chat.completions.create = MagicMock(side_effect=[rate_err, mock_ok])

            client = LLMClient.from_env(max_retries=2, rate_limit_delay=0.0)
            result = client.chat([{"role": "user", "content": "hi"}])

        assert result == "after-retry"
        assert client.stats.failed_attempt_count == 1
        assert client.stats.call_count == 1
        assert mock_sleep.called

    def test_rejects_call_from_running_loop(self, monkeypatch):
        """chat() must refuse to run from an active event loop; use AsyncLLMClient instead."""
        import asyncio

        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        async def _use_chat():
            LLMClient.from_env().chat([{"role": "user", "content": "hi"}])

        with pytest.raises(RuntimeError, match="running event loop"):
            asyncio.run(_use_chat())


class TestAsyncLLMClient:
    @pytest.mark.asyncio
    async def test_raises_on_no_providers(self):
        client = AsyncLLMClient.from_env()
        with pytest.raises(RuntimeError, match="No LLM providers"):
            await client.chat([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_successful_call(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "hello"
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_response)

            client = AsyncLLMClient.from_env()
            result = await client.chat([{"role": "user", "content": "hi"}])

        assert result == "hello"
        assert client.stats.call_count == 1

    @pytest.mark.asyncio
    async def test_chat_json(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"key": "value"}'
        mock_response.choices = [mock_choice]
        mock_response.usage = None

        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_response)

            client = AsyncLLMClient.from_env()
            result = await client.chat_json([{"role": "user", "content": "hi"}])

        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_rate_limit_retry(self, monkeypatch):
        from openai import RateLimitError

        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        mock_ok = MagicMock()
        mock_ok_choice = MagicMock()
        mock_ok_choice.message.content = "after-retry"
        mock_ok.choices = [mock_ok_choice]
        mock_ok.usage = None

        rate_err = RateLimitError("rate limit", response=MagicMock(headers={}), body=None)

        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client, \
             patch("auto_hub.llm.client.asyncio.sleep") as mock_sleep:
            instance = mock_client.return_value
            instance.chat.completions.create = AsyncMock(side_effect=[rate_err, mock_ok])

            client = AsyncLLMClient.from_env(max_retries=2, rate_limit_delay=0.0)
            result = await client.chat([{"role": "user", "content": "hi"}])

        assert result == "after-retry"
        assert client.stats.failed_attempt_count == 1
        assert client.stats.call_count == 1
        assert mock_sleep.called


# ---------------------------------------------------------------------------
# Extended provider support (Gemini, Azure OpenAI, Anthropic)
# ---------------------------------------------------------------------------


class TestProviderChainExtended:
    def test_gemini_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "GEMINI")
        monkeypatch.setenv("GEMINI_API_KEY", "key-g")
        monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-pro")
        monkeypatch.delenv("GEMINI_BASE_URL", raising=False)
        reset_provider_chain()
        chain = load_provider_chain()
        assert len(chain) == 1
        assert chain[0].name == "GEMINI"
        assert chain[0].model == "gemini-1.5-pro"
        # Native SDK providers do not require a base_url
        assert chain[0].base_url == ""

    def test_azure_openai_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "AZURE_OPENAI")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key-az")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://my-res.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_MODEL", "gpt-4o")
        reset_provider_chain()
        chain = load_provider_chain()
        assert len(chain) == 1
        assert chain[0].name == "AZURE_OPENAI"
        assert chain[0].base_url == "https://my-res.openai.azure.com"
        assert chain[0].model == "gpt-4o"

    def test_anthropic_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "ANTHROPIC")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key-ant")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3-sonnet")
        reset_provider_chain()
        chain = load_provider_chain()
        assert len(chain) == 1
        assert chain[0].name == "ANTHROPIC"
        assert chain[0].model == "claude-3-sonnet"


class TestAnthropicAdapter:
    def test_sync_message_format(self):
        from auto_hub.llm.adapters import AnthropicClientWrapper

        fake_msg = MagicMock()
        fake_msg.content = [MagicMock(text="hello from claude")]
        fake_msg.usage = MagicMock(input_tokens=10, output_tokens=5)

        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_msg

        wrapper = AnthropicClientWrapper(fake_client, "claude-3-sonnet")
        resp = wrapper.chat.completions.create(
            messages=[
                {"role": "system", "content": "be nice"},
                {"role": "user", "content": "hi"},
            ]
        )

        call_kwargs = fake_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "be nice"
        assert call_kwargs["messages"] == [{"role": "user", "content": "hi"}]
        assert call_kwargs["model"] == "claude-3-sonnet"
        assert resp.choices[0].message.content == "hello from claude"
        assert resp.usage.prompt_tokens == 10
        assert resp.usage.completion_tokens == 5

    @pytest.mark.asyncio
    async def test_async_message_format(self):
        from auto_hub.llm.adapters import AsyncAnthropicClientWrapper

        fake_msg = MagicMock()
        fake_msg.content = [MagicMock(text="async hello")]
        fake_msg.usage = MagicMock(input_tokens=8, output_tokens=4)

        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(return_value=fake_msg)

        wrapper = AsyncAnthropicClientWrapper(fake_client, "claude-3-opus")
        resp = await wrapper.chat.completions.create(
            messages=[{"role": "user", "content": "hello"}]
        )

        call_kwargs = fake_client.messages.create.call_args.kwargs
        assert call_kwargs["messages"] == [{"role": "user", "content": "hello"}]
        assert resp.choices[0].message.content == "async hello"

    def test_anthropic_requires_non_system_message(self):
        from auto_hub.llm.adapters import AnthropicClientWrapper

        fake_client = MagicMock()
        wrapper = AnthropicClientWrapper(fake_client, "claude-3")
        with pytest.raises(ValueError, match="non-system message"):
            wrapper.chat.completions.create(
                messages=[{"role": "system", "content": "only system"}]
            )

    def test_anthropic_ignores_response_format(self):
        from auto_hub.llm.adapters import AnthropicClientWrapper

        fake_msg = MagicMock()
        fake_msg.content = [MagicMock(text="ok")]
        fake_msg.usage = None

        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_msg

        wrapper = AnthropicClientWrapper(fake_client, "claude-3")
        resp = wrapper.chat.completions.create(
            messages=[{"role": "user", "content": "hi"}],
            response_format={"type": "json_object"},
        )
        assert resp.choices[0].message.content == "ok"

    def test_anthropic_sync_stream(self):
        from auto_hub.llm.adapters import AnthropicClientWrapper

        fake_event = MagicMock()
        fake_event.type = "content_block_delta"
        fake_event.delta = MagicMock(text="chunk1")

        fake_client = MagicMock()
        fake_client.messages.create.return_value = iter([fake_event])

        wrapper = AnthropicClientWrapper(fake_client, "claude-3")
        stream = wrapper.chat.completions.create(
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
        )
        chunks = list(stream)
        assert len(chunks) == 1
        assert chunks[0].choices[0].delta.content == "chunk1"

    @pytest.mark.asyncio
    async def test_anthropic_async_stream(self):
        from auto_hub.llm.adapters import AsyncAnthropicClientWrapper

        fake_event = MagicMock()
        fake_event.type = "content_block_delta"
        fake_event.delta = MagicMock(text="async-chunk")

        class _MockAsyncIter:
            def __init__(self, items):
                self._items = iter(items)
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration

        fake_stream = _MockAsyncIter([fake_event])
        fake_client = MagicMock()
        fake_client.messages.create = AsyncMock(return_value=fake_stream)

        wrapper = AsyncAnthropicClientWrapper(fake_client, "claude-3")
        stream = await wrapper.chat.completions.create(
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
        )
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        assert len(chunks) == 1
        assert chunks[0].choices[0].delta.content == "async-chunk"


class TestGeminiAdapter:
    def test_sync_message_format(self):
        from auto_hub.llm.adapters import GeminiClientWrapper

        fake_resp = MagicMock()
        fake_resp.candidates = [
            MagicMock(content=MagicMock(parts=[MagicMock(text="hello from gemini")]))
        ]
        fake_resp.usage_metadata = MagicMock(prompt_token_count=5, candidates_token_count=3)

        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = fake_resp

        wrapper = GeminiClientWrapper(fake_client, "gemini-1.5-pro")
        resp = wrapper.chat.completions.create(
            messages=[
                {"role": "system", "content": "be helpful"},
                {"role": "user", "content": "hi"},
            ]
        )

        call_kwargs = fake_client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-1.5-pro"
        assert resp.choices[0].message.content == "hello from gemini"
        assert resp.usage.prompt_tokens == 5
        assert resp.usage.completion_tokens == 3

    def test_gemini_sync_stream(self):
        from auto_hub.llm.adapters import GeminiClientWrapper

        fake_chunk = MagicMock()
        fake_chunk.text = "gemini-chunk"

        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = iter([fake_chunk])

        wrapper = GeminiClientWrapper(fake_client, "gemini-pro")
        stream = wrapper.chat.completions.create(
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
        )
        chunks = list(stream)
        assert len(chunks) == 1
        assert chunks[0].choices[0].delta.content == "gemini-chunk"

    @pytest.mark.asyncio
    async def test_async_message_format(self):
        from auto_hub.llm.adapters import AsyncGeminiClientWrapper

        fake_resp = MagicMock()
        fake_resp.candidates = [
            MagicMock(content=MagicMock(parts=[MagicMock(text="async gemini")]))
        ]
        fake_resp.usage_metadata = None

        fake_client = MagicMock()
        fake_client.aio.models.generate_content = AsyncMock(return_value=fake_resp)

        wrapper = AsyncGeminiClientWrapper(fake_client, "gemini-1.5-pro")
        resp = await wrapper.chat.completions.create(
            messages=[{"role": "user", "content": "hello"}]
        )
        assert resp.choices[0].message.content == "async gemini"

    @pytest.mark.asyncio
    async def test_gemini_async_stream(self):
        from auto_hub.llm.adapters import AsyncGeminiClientWrapper

        fake_chunk = MagicMock()
        fake_chunk.text = "async-gemini-chunk"

        class _MockAsyncIter:
            def __init__(self, items):
                self._items = iter(items)
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration

        fake_stream = _MockAsyncIter([fake_chunk])
        fake_client = MagicMock()
        fake_client.aio.models.generate_content = AsyncMock(return_value=fake_stream)

        wrapper = AsyncGeminiClientWrapper(fake_client, "gemini-pro")
        stream = await wrapper.chat.completions.create(
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
        )
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        assert len(chunks) == 1
        assert chunks[0].choices[0].delta.content == "async-gemini-chunk"


class TestStreaming:
    def test_chat_stream_sync(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="Hello "))]
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock(delta=MagicMock(content="world"))]
        chunk3 = MagicMock()
        chunk3.choices = [MagicMock(delta=MagicMock(content=""))]

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create.return_value = iter([chunk1, chunk2, chunk3])

            client = LLMClient.from_env()
            result = list(client.chat_stream([{"role": "user", "content": "hi"}]))

        assert result == ["Hello ", "world"]

    @pytest.mark.asyncio
    async def test_chat_stream_async(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="Async "))]
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock(delta=MagicMock(content="stream"))]

        class _MockAsyncIter:
            def __init__(self, items):
                self._items = iter(items)
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration

        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            instance = mock_client.return_value
            instance.chat.completions.create = AsyncMock(return_value=_MockAsyncIter([chunk1, chunk2]))

            client = AsyncLLMClient.from_env()
            result = []
            async for text in client.chat_stream([{"role": "user", "content": "hi"}]):
                result.append(text)

        assert result == ["Async ", "stream"]


# ---------------------------------------------------------------------------
# Responses API tests (OpenAI native)
# ---------------------------------------------------------------------------


class TestResponsesAPI:
    def test_response_sync(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        fake_resp = MagicMock()
        fake_resp.output_text = "Hello from Responses"

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.responses.create.return_value = fake_resp

            client = LLMClient.from_env()
            result = client.response("Tell me a joke")

        assert result == "Hello from Responses"
        call_kwargs = instance.responses.create.call_args.kwargs
        assert call_kwargs["model"] == "model-a"
        assert call_kwargs["input"] == "Tell me a joke"

    def test_response_with_instructions_and_tools(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        fake_resp = MagicMock()
        fake_resp.output_text = "tool result"

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.responses.create.return_value = fake_resp

            client = LLMClient.from_env()
            result = client.response(
                "Search the web",
                instructions="Be helpful",
                tools=[{"type": "web_search_preview"}],
            )

        assert result == "tool result"
        call_kwargs = instance.responses.create.call_args.kwargs
        assert call_kwargs["instructions"] == "Be helpful"
        assert call_kwargs["tools"] == [{"type": "web_search_preview"}]

    def test_response_stream_sync(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        e1 = MagicMock()
        e1.type = "response.output_text.delta"
        e1.delta = "Hello "
        e2 = MagicMock()
        e2.type = "response.output_text.delta"
        e2.delta = "Responses"

        with patch("auto_hub.llm.client.OpenAI") as mock_client:
            instance = mock_client.return_value
            instance.responses.create.return_value = iter([e1, e2])

            client = LLMClient.from_env()
            result = list(client.response_stream("Tell me a joke"))

        assert result == ["Hello ", "Responses"]

    def test_response_skips_non_openai_provider(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "ANTHROPIC,OPENAI")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key-ant")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3")
        monkeypatch.setenv("OPENAI_API_KEY", "key-oa")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                    "PROXY", "proxy", "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
            monkeypatch.delenv(key, raising=False)
        reset_provider_chain()

        fake_resp = MagicMock()
        fake_resp.output_text = "from openai"

        with patch("auto_hub.llm.client.OpenAI") as mock_openai:
            mock_openai.return_value.responses.create.return_value = fake_resp

            client = LLMClient.from_env()
            result = client.response("Hello")

        assert result == "from openai"
        # Anthropic has no responses attr, so it should be skipped silently

    def test_response_rejects_from_event_loop(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        import asyncio

        async def _call_response():
            LLMClient.from_env().response("hi")

        with pytest.raises(RuntimeError, match="running event loop"):
            asyncio.run(_call_response())

    def test_response_stream_rejects_from_event_loop(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        import asyncio

        async def _call_stream():
            # generator functions defer body execution until first next()
            gen = LLMClient.from_env().response_stream("hi")
            next(gen)

        with pytest.raises(RuntimeError, match="running event loop"):
            asyncio.run(_call_stream())

    @pytest.mark.asyncio
    async def test_response_async(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        fake_resp = MagicMock()
        fake_resp.output_text = "async response text"

        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            instance = mock_client.return_value
            instance.responses.create = AsyncMock(return_value=fake_resp)

            client = AsyncLLMClient.from_env()
            result = await client.response("Hello")

        assert result == "async response text"

    @pytest.mark.asyncio
    async def test_response_stream_async(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")

        e1 = MagicMock()
        e1.type = "response.output_text.delta"
        e1.delta = "Async "
        e2 = MagicMock()
        e2.type = "response.output_text.delta"
        e2.delta = "chunk"

        class _MockAsyncIter:
            def __init__(self, items):
                self._items = iter(items)
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration

        with patch("auto_hub.llm.client.AsyncOpenAI") as mock_client:
            instance = mock_client.return_value
            instance.responses.create = AsyncMock(return_value=_MockAsyncIter([e1, e2]))

            client = AsyncLLMClient.from_env()
            result = []
            async for text in client.response_stream("Hello"):
                result.append(text)

        assert result == ["Async ", "chunk"]


class TestResponseFallback:
    """Responses API fallback between compatible providers."""

    def test_response_fallback_to_next_openai_provider(self, monkeypatch):
        """RED: When first OpenAI provider fails, fallback to second OpenAI provider."""
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "OPENAI_A,OPENAI_B")
        monkeypatch.setenv("OPENAI_A_API_KEY", "key-a")
        monkeypatch.setenv("OPENAI_A_MODEL", "gpt-4o")
        monkeypatch.setenv("OPENAI_A_BASE_URL", "https://a.example.com/v1")
        monkeypatch.setenv("OPENAI_B_API_KEY", "key-b")
        monkeypatch.setenv("OPENAI_B_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("OPENAI_B_BASE_URL", "https://b.example.com/v1")
        reset_provider_chain()

        fake_resp = MagicMock()
        fake_resp.output_text = "from fallback"

        call_order = []

        def mock_openai_factory(**kwargs):
            base_url = kwargs.get("base_url", "")
            call_order.append(base_url)
            instance = MagicMock()
            if "a.example" in base_url:
                instance.responses.create.side_effect = Exception("primary down")
            else:
                instance.responses.create.return_value = fake_resp
            return instance

        with patch("auto_hub.llm.client.OpenAI", side_effect=mock_openai_factory):
            client = LLMClient.from_env()
            result = client.response("Hello")

        assert result == "from fallback"
        assert call_order == ["https://a.example.com/v1", "https://b.example.com/v1"]

    def test_response_all_incompatible_providers_raises(self, monkeypatch):
        """RED: When no provider supports responses, raise clear error."""
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "ANTHROPIC,GEMINI")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key-ant")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3")
        monkeypatch.setenv("GEMINI_API_KEY", "key-gem")
        monkeypatch.setenv("GEMINI_MODEL", "gemini-pro")
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                    "PROXY", "proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.delenv(key, raising=False)
        reset_provider_chain()

        client = LLMClient.from_env()
        with pytest.raises(RuntimeError, match="Responses API failed on all compatible"):
            client.response("Hello")


class TestChatStreamFallback:
    """Chat stream fallback when first provider fails."""

    def test_chat_stream_fallback_to_next_provider(self, monkeypatch):
        """RED: When first provider's stream fails, fallback to second."""
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "A,B")
        monkeypatch.setenv("A_API_KEY", "key-a")
        monkeypatch.setenv("A_MODEL", "model-a")
        monkeypatch.setenv("A_BASE_URL", "https://a.example.com/v1")
        monkeypatch.setenv("B_API_KEY", "key-b")
        monkeypatch.setenv("B_MODEL", "model-b")
        monkeypatch.setenv("B_BASE_URL", "https://b.example.com/v1")
        reset_provider_chain()

        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="fallback "))]
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock(delta=MagicMock(content="ok"))]

        call_order = []

        def mock_openai_factory(**kwargs):
            base_url = kwargs.get("base_url", "")
            call_order.append(base_url)
            instance = MagicMock()
            if "a.example" in base_url:
                instance.chat.completions.create.side_effect = Exception("stream broken")
            else:
                instance.chat.completions.create.return_value = [chunk1, chunk2]
            return instance

        with patch("auto_hub.llm.client.OpenAI", side_effect=mock_openai_factory):
            client = LLMClient.from_env()
            result = list(client.chat_stream([{"role": "user", "content": "hi"}]))

        assert result == ["fallback ", "ok"]
        assert call_order == ["https://a.example.com/v1", "https://b.example.com/v1"]


class TestAdapterParams:
    """Verify adapter-level parameter forwarding (temperature, max_tokens)."""

    def test_anthropic_temperature_forwarded(self):
        """RED: temperature kwarg must reach Anthropic messages.create."""
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="ok")]
        mock_client.messages.create.return_value = mock_msg

        adapter = AnthropicClientWrapper(mock_client, "claude-3")
        adapter.chat.completions.create(
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.5,
            max_tokens=100,
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 100

    def test_gemini_temperature_forwarded(self):
        """RED: temperature kwarg must reach Gemini generate_content config."""
        from google.genai import types

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.text = "ok"
        mock_client.models.generate_content.return_value = mock_response

        adapter = GeminiClientWrapper(mock_client, "gemini-pro")
        adapter.chat.completions.create(
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=200,
        )

        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        config = call_kwargs["config"]
        assert config.temperature == 0.7
        assert config.max_output_tokens == 200


class TestAdapterUsage:
    """Verify adapter response shims expose usage statistics."""

    def test_anthropic_usage_tokens(self):
        """RED: Anthropic adapter must expose prompt/completion token counts."""
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="hello")]
        mock_usage = MagicMock()
        mock_usage.input_tokens = 10
        mock_usage.output_tokens = 5
        mock_msg.usage = mock_usage
        mock_client.messages.create.return_value = mock_msg

        adapter = AnthropicClientWrapper(mock_client, "claude-3")
        resp = adapter.chat.completions.create(messages=[{"role": "user", "content": "hi"}])

        assert resp.usage.prompt_tokens == 10
        assert resp.usage.completion_tokens == 5

    def test_gemini_usage_tokens(self):
        """RED: Gemini adapter must expose prompt/completion token counts."""
        from google.genai import types

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.text = "hello"
        mock_usage = MagicMock()
        mock_usage.prompt_token_count = 20
        mock_usage.candidates_token_count = 8
        mock_response.usage_metadata = mock_usage
        mock_client.models.generate_content.return_value = mock_response

        adapter = GeminiClientWrapper(mock_client, "gemini-pro")
        resp = adapter.chat.completions.create(messages=[{"role": "user", "content": "hi"}])

        assert resp.usage.prompt_tokens == 20
        assert resp.usage.completion_tokens == 8

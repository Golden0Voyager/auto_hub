"""Tests for auto_hub.llm — provider chain, JSON parsing, stats, and client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auto_hub.llm import (
    AsyncLLMClient,
    CallStats,
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

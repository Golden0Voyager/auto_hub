from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any, TypeVar

from openai import AsyncOpenAI, OpenAI, RateLimitError
from openai.types.chat import ChatCompletionMessageParam

from auto_hub.llm.json import parse_llm_json
from auto_hub.llm.models import HARD_FAIL_PATTERNS, ProviderConfig
from auto_hub.llm.provider_chain import load_provider_chain, reset_provider_chain
from auto_hub.llm.stats import CallStats

logger = logging.getLogger("auto_hub.llm")

T = TypeVar("T")
RequestFn = Callable[[Any, dict[str, Any]], Awaitable[Any]]
SleepFn = Callable[[float], Awaitable[None]]


def _is_hard_fail(exc: Exception) -> bool:
    err_str = str(exc).lower()
    return any(pat in err_str for pat in HARD_FAIL_PATTERNS)


def _extract_retry_after(exc: RateLimitError) -> float | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    for key in ("retry-after", "Retry-After", "x-ratelimit-reset-requests"):
        value = headers.get(key) if hasattr(headers, "get") else None
        if not value:
            continue
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            continue
    return None


# Public alias for cross-package consumption
extract_retry_after = _extract_retry_after


def _build_openai_kwargs(config: ProviderConfig, *, async_client: bool) -> dict[str, Any]:
    """Build kwargs for sync (OpenAI) or async (AsyncOpenAI) clients.

    `async_client=True` returns `httpx.AsyncClient` for proxy support;
    otherwise returns `httpx.Client`.
    """
    kwargs: dict[str, Any] = {
        "api_key": config.api_key,
        "base_url": config.base_url,
    }
    proxy = os.getenv("PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if proxy:
        import httpx
        cls = httpx.AsyncClient if async_client else httpx.Client
        kwargs["http_client"] = cls(proxy=proxy)
    return kwargs


def _build_kwargs(
    effective_model: str,
    messages: list[ChatCompletionMessageParam],
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict[str, str] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": effective_model,
        "messages": messages,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if response_format is not None:
        kwargs["response_format"] = response_format
    return kwargs


def _process_response(resp: Any, stats: CallStats) -> str:
    content = resp.choices[0].message.content or ""
    usage = getattr(resp, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0 if usage else 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0 if usage else 0
    stats.record(prompt_tokens, completion_tokens)

    if content:
        return content

    msg = resp.choices[0].message
    reasoning = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)
    if reasoning:
        lines = reasoning.strip().splitlines()
        return lines[-1] if lines else ""

    return ""


class _ChainRunner:
    """Shared control flow for sync/async provider-chain iteration.

    Subclasses inject async `do_request` and `do_sleep` callables. The sync
    chat() path runs `_attempt_provider` via asyncio.run() with sync-wrapped
    callables; the async path awaits it directly.
    """

    def __init__(self, stats: CallStats, max_retries: int, rate_limit_delay: float):
        self.stats = stats
        self.max_retries = max_retries
        self.rate_limit_delay = rate_limit_delay

    async def _attempt_provider(
        self,
        provider: ProviderConfig,
        client: Any,
        request: RequestFn,
        sleep: SleepFn,
        *,
        model: str | None,
        messages: list[ChatCompletionMessageParam],
        temperature: float | None,
        max_tokens: int | None,
        response_format: dict[str, str] | None,
    ) -> tuple[bool, str | None, Exception | None]:
        """Run all retries against one provider. Returns (success, content, last_error)."""
        effective_model = model or provider.model
        if not effective_model:
            logger.warning("No model specified for %s, skipping", provider.name)
            return (False, None, None)

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs = _build_kwargs(effective_model, messages, temperature, max_tokens, response_format)
                resp = await request(client, kwargs)
                return (True, _process_response(resp, self.stats), None)

            except RateLimitError as exc:
                self.stats.record_failure()
                last_error = exc
                retry_after = _extract_retry_after(exc)
                wait = retry_after if retry_after else self.rate_limit_delay * (2 ** (attempt - 1))
                logger.warning("Rate limited by %s (attempt %d), waiting %.1fs", provider.name, attempt, wait)
                if attempt < self.max_retries:
                    await sleep(wait)
                    continue
                break

            except Exception as exc:
                self.stats.record_failure()
                last_error = exc

                if _is_hard_fail(exc):
                    logger.error("Hard fail on %s: %s", provider.name, exc)
                    break

                if attempt < self.max_retries:
                    logger.warning("Error from %s (attempt %d): %s", provider.name, attempt, exc)
                    await sleep(self.rate_limit_delay * (2 ** (attempt - 1)))
                    continue

        return (False, None, last_error)


class LLMClient:
    """Sync OpenAI-compatible LLM client with provider chain, retry, and stats."""

    def __init__(
        self,
        *,
        max_retries: int = 2,
        rate_limit_delay: float = 2.0,
    ):
        self.max_retries = max_retries
        self.rate_limit_delay = rate_limit_delay
        self.stats = CallStats()
        self._client_cache: dict[str, OpenAI] = {}
        self._runner = _ChainRunner(self.stats, max_retries, rate_limit_delay)

    @classmethod
    def from_env(cls, **kwargs: Any) -> LLMClient:
        return cls(**kwargs)

    def _get_client(self, config: ProviderConfig) -> Any:
        if config.name.startswith("ANTHROPIC"):
            from anthropic import Anthropic
            from auto_hub.llm.adapters import AnthropicClientWrapper
            return AnthropicClientWrapper(Anthropic(api_key=config.api_key), config.model)

        if config.name.startswith("GEMINI"):
            from google import genai
            from auto_hub.llm.adapters import GeminiClientWrapper
            return GeminiClientWrapper(genai.Client(api_key=config.api_key), config.model)

        if config.name.startswith("AZURE"):
            from openai import AzureOpenAI
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
            cache_key = f"{config.name}:{config.base_url}:{api_version}"
            if cache_key not in self._client_cache:
                kwargs: dict[str, Any] = {
                    "api_key": config.api_key,
                    "api_version": api_version,
                    "azure_endpoint": config.base_url,
                    "timeout": 180.0,
                }
                proxy = os.getenv("PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
                if proxy:
                    import httpx
                    kwargs["http_client"] = httpx.Client(proxy=proxy)
                self._client_cache[cache_key] = AzureOpenAI(**kwargs)
            return self._client_cache[cache_key]

        cache_key = f"{config.name}:{config.base_url}"
        if cache_key not in self._client_cache:
            self._client_cache[cache_key] = OpenAI(
                **{**_build_openai_kwargs(config, async_client=False), "timeout": 180.0}
            )
        return self._client_cache[cache_key]

    def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
    ) -> str:
        """Synchronous entry point. Internally runs the async chain via asyncio.run.

        Must be called from a non-async context. If you need to call LLM from
        inside an event loop, use AsyncLLMClient instead.
        """
        try:
            asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False
        if in_loop:
            raise RuntimeError(
                "LLMClient.chat() cannot be called from a running event loop; "
                "use AsyncLLMClient in async contexts."
            )
        return asyncio.run(self._achat(messages, model=model, temperature=temperature,
                                       max_tokens=max_tokens, response_format=response_format))

    async def _achat(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
        response_format: dict[str, str] | None,
    ) -> str:
        chain = load_provider_chain()
        if not chain:
            raise RuntimeError("No LLM providers configured (check AI_PROVIDER_CHAIN)")

        def request_sync(client: OpenAI, kwargs: dict[str, Any]) -> Any:
            return client.chat.completions.create(**kwargs)

        async def request(client: OpenAI, kwargs: dict[str, Any]) -> Any:
            return request_sync(client, kwargs)

        def sleep_sync(seconds: float) -> None:
            time.sleep(seconds)

        async def sleep(seconds: float) -> None:
            sleep_sync(seconds)

        last_error: Exception | None = None

        for provider in chain:
            client = self._get_client(provider)
            success, content, err = await self._runner._attempt_provider(
                provider, client, request, sleep,
                model=model, messages=messages,
                temperature=temperature, max_tokens=max_tokens, response_format=response_format,
            )
            if success:
                assert content is not None
                return content
            if err is not None:
                last_error = err

        raise RuntimeError(f"All LLM providers exhausted. Last error: {last_error}")

    def chat_json(
        self,
        messages: list[ChatCompletionMessageParam],
        **kwargs: Any,
    ) -> Any:
        raw = self.chat(messages, **kwargs)
        return parse_llm_json(raw)

    def chat_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
    ) -> Iterator[str]:
        """Stream response text chunks from the LLM.

        Iterates over the provider chain; yields each content chunk as it
        arrives. Falls back to the next provider if the current one fails
        to establish a stream.
        """
        try:
            asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False
        if in_loop:
            raise RuntimeError(
                "LLMClient.chat_stream() cannot be called from a running event loop; "
                "use AsyncLLMClient.chat_stream() in async contexts."
            )

        chain = load_provider_chain()
        if not chain:
            raise RuntimeError("No LLM providers configured (check AI_PROVIDER_CHAIN)")

        for provider in chain:
            client = self._get_client(provider)
            try:
                effective_model = model or provider.model
                if not effective_model:
                    logger.warning("No model specified for %s, skipping", provider.name)
                    continue
                kwargs = _build_kwargs(
                    effective_model, messages, temperature, max_tokens, response_format
                )
                kwargs["stream"] = True
                stream = client.chat.completions.create(**kwargs)
                for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        yield content
                return
            except Exception as exc:
                logger.warning("Streaming failed on %s: %s", provider.name, exc)
                continue

        raise RuntimeError("All providers exhausted for streaming")

    def response(
        self,
        input_text: str,
        *,
        model: str | None = None,
        instructions: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """Call OpenAI Responses API (non-streaming).

        Only providers whose client exposes a ``responses`` attribute
        (e.g. OpenAI, Azure OpenAI) are attempted; others are skipped.
        """
        try:
            asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False
        if in_loop:
            raise RuntimeError(
                "LLMClient.response() cannot be called from a running event loop; "
                "use AsyncLLMClient.response() in async contexts."
            )

        chain = load_provider_chain()
        if not chain:
            raise RuntimeError("No LLM providers configured (check AI_PROVIDER_CHAIN)")

        last_error: Exception | None = None
        for provider in chain:
            client = self._get_client(provider)
            if not hasattr(client, "responses"):
                continue
            try:
                effective_model = model or provider.model
                if not effective_model:
                    logger.warning("No model specified for %s, skipping", provider.name)
                    continue
                kwargs: dict[str, Any] = {"model": effective_model, "input": input_text}
                if instructions:
                    kwargs["instructions"] = instructions
                if tools:
                    kwargs["tools"] = tools
                resp = client.responses.create(**kwargs)
                return resp.output_text
            except Exception as exc:
                logger.warning("Responses API failed on %s: %s", provider.name, exc)
                last_error = exc
                continue

        raise RuntimeError(
            f"Responses API failed on all compatible providers. Last error: {last_error}"
        )

    def response_stream(
        self,
        input_text: str,
        *,
        model: str | None = None,
        instructions: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[str]:
        """Call OpenAI Responses API with streaming.

        Yields text chunks as they arrive. Only providers whose client
        exposes a ``responses`` attribute are attempted.
        """
        try:
            asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False
        if in_loop:
            raise RuntimeError(
                "LLMClient.response_stream() cannot be called from a running event loop; "
                "use AsyncLLMClient.response_stream() in async contexts."
            )

        chain = load_provider_chain()
        if not chain:
            raise RuntimeError("No LLM providers configured (check AI_PROVIDER_CHAIN)")

        for provider in chain:
            client = self._get_client(provider)
            if not hasattr(client, "responses"):
                continue
            try:
                effective_model = model or provider.model
                if not effective_model:
                    logger.warning("No model specified for %s, skipping", provider.name)
                    continue
                kwargs: dict[str, Any] = {
                    "model": effective_model,
                    "input": input_text,
                    "stream": True,
                }
                if instructions:
                    kwargs["instructions"] = instructions
                if tools:
                    kwargs["tools"] = tools
                for event in client.responses.create(**kwargs):
                    if getattr(event, "type", "") == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            yield delta
                return
            except Exception as exc:
                logger.warning("Responses API streaming failed on %s: %s", provider.name, exc)
                continue

        raise RuntimeError("Responses API streaming failed on all compatible providers")

    def reset_cache(self) -> None:
        self._client_cache.clear()
        reset_provider_chain()


class AsyncLLMClient:
    """Async OpenAI-compatible LLM client with provider chain, retry, and stats."""

    def __init__(
        self,
        *,
        max_retries: int = 2,
        rate_limit_delay: float = 2.0,
    ):
        self.max_retries = max_retries
        self.rate_limit_delay = rate_limit_delay
        self.stats = CallStats()
        self._client_cache: dict[str, AsyncOpenAI] = {}
        self._runner = _ChainRunner(self.stats, max_retries, rate_limit_delay)

    @classmethod
    def from_env(cls, **kwargs: Any) -> AsyncLLMClient:
        return cls(**kwargs)

    def _get_client(self, config: ProviderConfig) -> Any:
        if config.name.startswith("ANTHROPIC"):
            from anthropic import AsyncAnthropic
            from auto_hub.llm.adapters import AsyncAnthropicClientWrapper
            return AsyncAnthropicClientWrapper(AsyncAnthropic(api_key=config.api_key), config.model)

        if config.name.startswith("GEMINI"):
            from google import genai
            from auto_hub.llm.adapters import AsyncGeminiClientWrapper
            return AsyncGeminiClientWrapper(genai.Client(api_key=config.api_key), config.model)

        if config.name.startswith("AZURE"):
            from openai import AsyncAzureOpenAI
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
            cache_key = f"{config.name}:{config.base_url}:{api_version}"
            if cache_key not in self._client_cache:
                kwargs: dict[str, Any] = {
                    "api_key": config.api_key,
                    "api_version": api_version,
                    "azure_endpoint": config.base_url,
                    "timeout": 180.0,
                }
                proxy = os.getenv("PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
                if proxy:
                    import httpx
                    kwargs["http_client"] = httpx.AsyncClient(proxy=proxy)
                self._client_cache[cache_key] = AsyncAzureOpenAI(**kwargs)
            return self._client_cache[cache_key]

        cache_key = f"{config.name}:{config.base_url}"
        if cache_key not in self._client_cache:
            self._client_cache[cache_key] = AsyncOpenAI(
                **{**_build_openai_kwargs(config, async_client=True), "timeout": 180.0}
            )
        return self._client_cache[cache_key]

    async def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
    ) -> str:
        chain = load_provider_chain()
        if not chain:
            raise RuntimeError("No LLM providers configured (check AI_PROVIDER_CHAIN)")

        async def request(client: AsyncOpenAI, kwargs: dict[str, Any]) -> Any:
            return await client.chat.completions.create(**kwargs)

        async def sleep(seconds: float) -> None:
            await asyncio.sleep(seconds)

        last_error: Exception | None = None

        for provider in chain:
            client = self._get_client(provider)
            success, content, err = await self._runner._attempt_provider(
                provider, client, request, sleep,
                model=model, messages=messages,
                temperature=temperature, max_tokens=max_tokens, response_format=response_format,
            )
            if success:
                assert content is not None
                return content
            if err is not None:
                last_error = err

        raise RuntimeError(f"All LLM providers exhausted. Last error: {last_error}")

    async def chat_json(
        self,
        messages: list[ChatCompletionMessageParam],
        **kwargs: Any,
    ) -> Any:
        raw = await self.chat(messages, **kwargs)
        return parse_llm_json(raw)

    async def chat_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
    ) -> AsyncIterator[str]:
        """Async stream response text chunks from the LLM.

        Iterates over the provider chain; yields each content chunk as it
        arrives. Falls back to the next provider if the current one fails
        to establish a stream.
        """
        chain = load_provider_chain()
        if not chain:
            raise RuntimeError("No LLM providers configured (check AI_PROVIDER_CHAIN)")

        for provider in chain:
            client = self._get_client(provider)
            try:
                effective_model = model or provider.model
                if not effective_model:
                    logger.warning("No model specified for %s, skipping", provider.name)
                    continue
                kwargs = _build_kwargs(
                    effective_model, messages, temperature, max_tokens, response_format
                )
                kwargs["stream"] = True
                stream = await client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        yield content
                return
            except Exception as exc:
                logger.warning("Streaming failed on %s: %s", provider.name, exc)
                continue

        raise RuntimeError("All providers exhausted for streaming")

    async def response(
        self,
        input_text: str,
        *,
        model: str | None = None,
        instructions: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """Async call OpenAI Responses API (non-streaming).

        Only providers whose client exposes a ``responses`` attribute
        (e.g. OpenAI, Azure OpenAI) are attempted; others are skipped.
        """
        chain = load_provider_chain()
        if not chain:
            raise RuntimeError("No LLM providers configured (check AI_PROVIDER_CHAIN)")

        last_error: Exception | None = None
        for provider in chain:
            client = self._get_client(provider)
            if not hasattr(client, "responses"):
                continue
            try:
                effective_model = model or provider.model
                if not effective_model:
                    logger.warning("No model specified for %s, skipping", provider.name)
                    continue
                kwargs: dict[str, Any] = {"model": effective_model, "input": input_text}
                if instructions:
                    kwargs["instructions"] = instructions
                if tools:
                    kwargs["tools"] = tools
                resp = await client.responses.create(**kwargs)
                return resp.output_text
            except Exception as exc:
                logger.warning("Responses API failed on %s: %s", provider.name, exc)
                last_error = exc
                continue

        raise RuntimeError(
            f"Responses API failed on all compatible providers. Last error: {last_error}"
        )

    async def response_stream(
        self,
        input_text: str,
        *,
        model: str | None = None,
        instructions: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Async call OpenAI Responses API with streaming.

        Yields text chunks as they arrive.
        """
        chain = load_provider_chain()
        if not chain:
            raise RuntimeError("No LLM providers configured (check AI_PROVIDER_CHAIN)")

        for provider in chain:
            client = self._get_client(provider)
            if not hasattr(client, "responses"):
                continue
            try:
                effective_model = model or provider.model
                if not effective_model:
                    logger.warning("No model specified for %s, skipping", provider.name)
                    continue
                kwargs: dict[str, Any] = {
                    "model": effective_model,
                    "input": input_text,
                    "stream": True,
                }
                if instructions:
                    kwargs["instructions"] = instructions
                if tools:
                    kwargs["tools"] = tools
                stream = await client.responses.create(**kwargs)
                async for event in stream:
                    if getattr(event, "type", "") == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            yield delta
                return
            except Exception as exc:
                logger.warning("Responses API streaming failed on %s: %s", provider.name, exc)
                continue

        raise RuntimeError("Responses API streaming failed on all compatible providers")

    def reset_cache(self) -> None:
        self._client_cache.clear()
        reset_provider_chain()

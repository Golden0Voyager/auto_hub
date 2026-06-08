"""Thin adapters for non-OpenAI-compatible LLM providers.

Exposes a unified ``chat.completions.create`` interface so the rest of
``auto_hub.llm.client`` can stay provider-agnostic.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Shared streaming shim
# ---------------------------------------------------------------------------


class _StreamChunk:
    def __init__(self, text: str) -> None:
        self.choices = [_StreamChoice(text)]


class _StreamChoice:
    def __init__(self, text: str) -> None:
        self.delta = _StreamDelta(text)
        self.index = 0


class _StreamDelta:
    def __init__(self, text: str) -> None:
        self.content = text


# ---------------------------------------------------------------------------
# Anthropic response shims
# ---------------------------------------------------------------------------


class _AnthropicMessage:
    def __init__(self, raw: Any) -> None:
        self._raw = raw
        content_blocks = getattr(raw, "content", [])
        self.content = content_blocks[0].text if content_blocks else ""
        self.reasoning_content = getattr(raw, "thinking", "") or ""


class _AnthropicChoice:
    def __init__(self, raw: Any) -> None:
        self.message = _AnthropicMessage(raw)


class _AnthropicUsage:
    def __init__(self, raw: Any) -> None:
        self.prompt_tokens = getattr(raw, "input_tokens", 0) or 0
        self.completion_tokens = getattr(raw, "output_tokens", 0) or 0


class _AnthropicResponse:
    def __init__(self, raw: Any) -> None:
        self._raw = raw
        self.choices = [_AnthropicChoice(raw)]
        usage = getattr(raw, "usage", None)
        self.usage = _AnthropicUsage(usage) if usage else None


# ---------------------------------------------------------------------------
# Anthropic helpers
# ---------------------------------------------------------------------------


def _build_anthropic_api_kwargs(
    *, default_model: str, **kwargs: Any
) -> dict[str, Any]:
    messages = kwargs.get("messages", [])
    model = kwargs.get("model") or default_model
    max_tokens = kwargs.get("max_tokens", 4096)
    temperature = kwargs.get("temperature")

    system: str | None = None
    anthropic_messages: list[dict[str, str]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            system = msg.get("content")
        elif role in ("user", "assistant"):
            anthropic_messages.append({"role": role, "content": msg.get("content", "")})

    if not anthropic_messages:
        raise ValueError("At least one non-system message is required for Anthropic")

    api_kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": anthropic_messages,
    }
    if system:
        api_kwargs["system"] = system
    if temperature is not None:
        api_kwargs["temperature"] = temperature
    return api_kwargs


# ---------------------------------------------------------------------------
# Sync Anthropic wrapper
# ---------------------------------------------------------------------------


class _AnthropicChatCompletions:
    def __init__(self, client: Any, default_model: str) -> None:
        self._client = client
        self._default_model = default_model

    def create(self, **kwargs: Any) -> Any:
        if kwargs.pop("stream", False):
            return self._stream(**kwargs)

        api_kwargs = _build_anthropic_api_kwargs(default_model=self._default_model, **kwargs)
        raw = self._client.messages.create(**api_kwargs)
        return _AnthropicResponse(raw)

    def _stream(self, **kwargs: Any):
        api_kwargs = _build_anthropic_api_kwargs(default_model=self._default_model, **kwargs)
        api_kwargs["stream"] = True
        for event in self._client.messages.create(**api_kwargs):
            if getattr(event, "type", "") == "content_block_delta":
                text = getattr(getattr(event, "delta", None), "text", "")
                if text:
                    yield _StreamChunk(text)


class AnthropicClientWrapper:
    """Wraps an Anthropic sync client to look like an OpenAI client."""

    def __init__(self, client: Any, model: str) -> None:
        self.chat = type("Chat", (), {"completions": _AnthropicChatCompletions(client, model)})()


# ---------------------------------------------------------------------------
# Async Anthropic wrapper
# ---------------------------------------------------------------------------


class _AsyncAnthropicChatCompletions:
    def __init__(self, client: Any, default_model: str) -> None:
        self._client = client
        self._default_model = default_model

    async def create(self, **kwargs: Any) -> Any:
        if kwargs.pop("stream", False):
            return self._stream(**kwargs)

        api_kwargs = _build_anthropic_api_kwargs(default_model=self._default_model, **kwargs)
        raw = await self._client.messages.create(**api_kwargs)
        return _AnthropicResponse(raw)

    async def _stream(self, **kwargs: Any):
        api_kwargs = _build_anthropic_api_kwargs(default_model=self._default_model, **kwargs)
        api_kwargs["stream"] = True
        stream = await self._client.messages.create(**api_kwargs)
        async for event in stream:
            if getattr(event, "type", "") == "content_block_delta":
                text = getattr(getattr(event, "delta", None), "text", "")
                if text:
                    yield _StreamChunk(text)


class AsyncAnthropicClientWrapper:
    """Wraps an Anthropic async client to look like an OpenAI client."""

    def __init__(self, client: Any, model: str) -> None:
        self.chat = type("Chat", (), {"completions": _AsyncAnthropicChatCompletions(client, model)})()


# ---------------------------------------------------------------------------
# Google Gemini response shims
# ---------------------------------------------------------------------------


class _GeminiMessage:
    def __init__(self, raw: Any) -> None:
        self._raw = raw
        candidates = getattr(raw, "candidates", [])
        if candidates and hasattr(candidates[0], "content"):
            parts = getattr(candidates[0].content, "parts", [])
            self.content = "".join(
                p.text for p in parts if hasattr(p, "text")
            )
        else:
            self.content = getattr(raw, "text", "") or ""
        self.reasoning_content = ""


class _GeminiChoice:
    def __init__(self, raw: Any) -> None:
        self.message = _GeminiMessage(raw)
        self.index = 0


class _GeminiUsage:
    def __init__(self, raw: Any) -> None:
        self.prompt_tokens = getattr(raw, "prompt_token_count", 0) or 0
        self.completion_tokens = getattr(raw, "candidates_token_count", 0) or 0


class _GeminiResponse:
    def __init__(self, raw: Any) -> None:
        self._raw = raw
        self.choices = [_GeminiChoice(raw)]
        usage_meta = getattr(raw, "usage_metadata", None)
        self.usage = _GeminiUsage(usage_meta) if usage_meta else None


# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------


def _build_gemini_config(**kwargs: Any) -> tuple[list[Any], Any]:
    from google.genai import types

    messages = kwargs.get("messages", [])
    temperature = kwargs.get("temperature")
    max_tokens = kwargs.get("max_tokens")

    system_instruction: str | None = None
    contents: list[Any] = []
    for msg in messages:
        role = msg.get("role")
        text = msg.get("content", "")
        if role == "system":
            system_instruction = text
        elif role == "user":
            contents.append(
                types.Content(role="user", parts=[types.Part(text=text)])
            )
        elif role == "assistant":
            contents.append(
                types.Content(role="model", parts=[types.Part(text=text)])
            )

    config = types.GenerateContentConfig()
    if system_instruction:
        config.system_instruction = system_instruction
    if temperature is not None:
        config.temperature = temperature
    if max_tokens is not None:
        config.max_output_tokens = max_tokens
    return contents or [types.Content(role="user", parts=[types.Part(text="")])], config


# ---------------------------------------------------------------------------
# Sync Gemini wrapper
# ---------------------------------------------------------------------------


class _GeminiChatCompletions:
    def __init__(self, client: Any, default_model: str) -> None:
        self._client = client
        self._default_model = default_model

    def create(self, **kwargs: Any) -> Any:
        if kwargs.pop("stream", False):
            return self._stream(**kwargs)

        model = kwargs.get("model") or self._default_model
        contents, config = _build_gemini_config(**kwargs)
        raw = self._client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        return _GeminiResponse(raw)

    def _stream(self, **kwargs: Any):
        model = kwargs.get("model") or self._default_model
        contents, config = _build_gemini_config(**kwargs)
        for chunk in self._client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
            stream=True,
        ):
            text = getattr(chunk, "text", "") or ""
            if text:
                yield _StreamChunk(text)


class GeminiClientWrapper:
    """Wraps a google-genai sync client to look like an OpenAI client."""

    def __init__(self, client: Any, model: str) -> None:
        self.chat = type("Chat", (), {"completions": _GeminiChatCompletions(client, model)})()


# ---------------------------------------------------------------------------
# Async Gemini wrapper
# ---------------------------------------------------------------------------


class _AsyncGeminiChatCompletions:
    def __init__(self, client: Any, default_model: str) -> None:
        self._client = client
        self._default_model = default_model

    async def create(self, **kwargs: Any) -> Any:
        if kwargs.pop("stream", False):
            return self._stream(**kwargs)

        model = kwargs.get("model") or self._default_model
        contents, config = _build_gemini_config(**kwargs)
        raw = await self._client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        return _GeminiResponse(raw)

    async def _stream(self, **kwargs: Any):
        model = kwargs.get("model") or self._default_model
        contents, config = _build_gemini_config(**kwargs)
        stream = await self._client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
            stream=True,
        )
        async for chunk in stream:
            text = getattr(chunk, "text", "") or ""
            if text:
                yield _StreamChunk(text)


class AsyncGeminiClientWrapper:
    """Wraps a google-genai async client to look like an OpenAI client."""

    def __init__(self, client: Any, model: str) -> None:
        self.chat = type("Chat", (), {"completions": _AsyncGeminiChatCompletions(client, model)})()

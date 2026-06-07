"""Tests for the MCP aggregation gateway."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from auto_hub.llm.provider_chain import reset_provider_chain
from auto_hub.mcp.gateway import GatewayStats, _gateway_stats, create_app


def test_create_app():
    app = create_app()
    assert app.name == "auto-hub"
    assert app.instructions


@pytest.mark.asyncio
async def test_list_projects_tool():
    app = create_app()
    content, meta = await app.call_tool("list_projects", {})
    text = content[0].text
    assert "auto_pdf" in text
    assert "auto_scrape" in text
    assert "auto_nutrition" in text


@pytest.mark.asyncio
async def test_show_project_tool():
    app = create_app()
    content, meta = await app.call_tool("show_project", {"name": "auto_pdf"})
    text = content[0].text
    assert "auto_pdf" in text
    assert "[EXISTS]" in text or "[MISSING]" in text


@pytest.mark.asyncio
async def test_show_project_not_found():
    app = create_app()
    content, meta = await app.call_tool("show_project", {"name": "nonexistent"})
    assert "not found" in content[0].text


@pytest.mark.asyncio
async def test_registry_status_tool():
    app = create_app()
    content, meta = await app.call_tool("registry_status", {})
    text = content[0].text
    assert "Total projects" in text
    assert "By type" in text


@pytest.mark.asyncio
async def test_provider_chain_tool_empty():
    reset_provider_chain()
    app = create_app()
    with patch.dict("os.environ", {}, clear=True):
        content, meta = await app.call_tool("provider_chain", {})
    assert "No providers configured" in content[0].text


@pytest.mark.asyncio
async def test_provider_chain_tool_configured():
    reset_provider_chain()
    app = create_app()
    env = {
        "AI_PROVIDER_CHAIN": "OPENAI,SENSENOVA",
        "OPENAI_API_KEY": "sk-test-openai",
        "SENSENOVA_API_KEY": "sk-test-sensenova",
    }
    with patch.dict("os.environ", env, clear=True):
        content, meta = await app.call_tool("provider_chain", {})
    text = content[0].text
    assert "openai" in text.lower()
    assert "sensenova" in text.lower()
    assert "(primary)" in text
    assert "(fallback)" in text


@pytest.mark.asyncio
async def test_llm_chat_no_env():
    reset_provider_chain()
    app = create_app()
    with patch.dict("os.environ", {}, clear=True):
        content, meta = await app.call_tool("llm_chat", {"message": "hello"})
    assert "LLM error" in content[0].text


@pytest.mark.asyncio
async def test_llm_stats():
    app = create_app()
    _gateway_stats.reset()
    content, meta = await app.call_tool("llm_stats", {})
    assert '"llm_calls": 0' in content[0].text


@pytest.mark.asyncio
async def test_reset_llm_stats():
    app = create_app()
    _gateway_stats.llm_calls = 5
    _gateway_stats.llm_failures = 2
    content, meta = await app.call_tool("reset_llm_stats", {})
    assert "reset" in content[0].text
    assert _gateway_stats.llm_calls == 0
    assert _gateway_stats.llm_failures == 0


def test_gateway_stats():
    stats = GatewayStats()
    assert stats.snapshot() == {"llm_calls": 0, "llm_failures": 0}
    stats.llm_calls = 3
    stats.llm_failures = 1
    snap = stats.snapshot()
    assert snap["llm_calls"] == 3
    assert snap["llm_failures"] == 1
    stats.reset()
    assert stats.llm_calls == 0


@pytest.mark.asyncio
async def test_llm_chat_tracks_stats():
    reset_provider_chain()
    app = create_app()
    _gateway_stats.reset()
    with patch.dict("os.environ", {}, clear=True):
        await app.call_tool("llm_chat", {"message": "hi"})
    snap = _gateway_stats.snapshot()
    assert snap["llm_calls"] == 1
    assert snap["llm_failures"] == 1


@pytest.mark.asyncio
async def test_llm_chat_success(monkeypatch):
    """Happy path: hub returns a response → gateway relays it and stats increment correctly."""
    from auto_hub.mcp import gateway

    reset_provider_chain()
    app = create_app()
    gateway._gateway_stats.reset()

    fake_client = MagicMock()
    fake_client.chat.return_value = "ok-from-hub"
    monkeypatch.setattr(gateway, "_get_llm_client", lambda: fake_client)

    content, _meta = await app.call_tool("llm_chat", {"message": "ping"})
    assert content[0].text == "ok-from-hub"
    snap = gateway._gateway_stats.snapshot()
    assert snap["llm_calls"] == 1
    assert snap["llm_failures"] == 0


@pytest.mark.asyncio
async def test_llm_chat_runtime_error_returns_error(monkeypatch):
    """Hub raises RuntimeError → gateway returns formatted error, no exception propagates."""
    from auto_hub.mcp import gateway

    reset_provider_chain()
    app = create_app()
    gateway._gateway_stats.reset()

    fake_client = MagicMock()
    fake_client.chat.side_effect = RuntimeError("all providers exhausted")
    monkeypatch.setattr(gateway, "_get_llm_client", lambda: fake_client)

    content, _meta = await app.call_tool("llm_chat", {"message": "ping"})
    assert "LLM error" in content[0].text
    assert "all providers exhausted" in content[0].text
    assert gateway._gateway_stats.llm_failures == 1

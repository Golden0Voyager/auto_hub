"""MCP aggregation gateway for auto_hub.

Exposes auto_hub capabilities (registry, LLM) as MCP tools via FastMCP.
Run with: auto-hub mcp
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from auto_hub.llm.client import LLMClient
from auto_hub.llm.provider_chain import load_provider_chain
from auto_hub.registry.loader import RegistryLoader

mcp = FastMCP("auto-hub", instructions="auto_hub MCP gateway — registry queries and LLM access")


@dataclass
class GatewayStats:
    llm_calls: int = 0
    llm_failures: int = 0

    def snapshot(self) -> dict[str, int]:
        return {"llm_calls": self.llm_calls, "llm_failures": self.llm_failures}

    def reset(self) -> None:
        self.llm_calls = 0
        self.llm_failures = 0


_gateway_stats = GatewayStats()
_llm_client: LLMClient | None = None


def _get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient.from_env()
    return _llm_client


def _loader() -> RegistryLoader:
    return RegistryLoader()


@mcp.tool()
def list_projects() -> str:
    """List all registered auto_* projects."""
    loader = _loader()
    projects = loader.list_projects()
    lines = []
    for p in sorted(projects, key=lambda x: x.name):
        label = f"  {p.name}"
        label += f"  ({p.type})"
        label += f"  — {p.description}"
        resolved = loader.resolve_path(p)
        if not resolved.exists():
            label += "  [MISSING]"
        lines.append(label)
    return "\n".join(lines) if lines else "No projects registered."


@mcp.tool()
def show_project(name: str) -> str:
    """Show details for a specific auto_* project by name."""
    loader = _loader()
    project = loader.get_project(name)
    if project is None:
        return f"Project '{name}' not found."

    resolved = loader.resolve_path(project)
    exists = resolved.exists()
    lines = [
        f"Name:        {project.name}",
        f"Type:        {project.type}",
        f"Status:      {project.status}",
        f"Description: {project.description}",
        f"Path:        {project.path}",
        f"Resolved:    {resolved} {'[EXISTS]' if exists else '[MISSING]'}",
    ]
    if project.capabilities:
        lines.append(f"Capabilities ({len(project.capabilities)}):")
        for cap in project.capabilities:
            lines.append(f"  - {cap}")
    if project.entrypoints:
        lines.append("Entry points:")
        if project.entrypoints.cli:
            lines.append(f"  CLI:   {project.entrypoints.cli.command}")
        if project.entrypoints.web:
            lines.append(f"  Web:   {project.entrypoints.web.command}")
        if project.entrypoints.mcp:
            lines.append(f"  MCP:   {project.entrypoints.mcp.command}")
    return "\n".join(lines)


@mcp.tool()
def registry_status() -> str:
    """Show status summary of all registered projects."""
    loader = _loader()
    projects = loader.list_projects()
    missing = loader.get_missing_projects()

    total = len(projects)
    present = total - len(missing)

    by_type: dict[str, int] = {}
    for p in projects:
        by_type[p.type] = by_type.get(p.type, 0) + 1

    lines = [
        f"Total projects:  {total}",
        f"Present:         {present}",
        f"Missing:         {len(missing)}",
        "---",
        "By type:",
    ]
    for t, count in sorted(by_type.items()):
        lines.append(f"  {t}: {count}")
    if missing:
        lines.append("---\nMissing projects:")
        for m in missing:
            lines.append(f"  {m.name} ({m.path})")
    return "\n".join(lines)


@mcp.tool()
def llm_chat(message: str, model: str | None = None) -> str:
    """Send a chat message through auto_hub.llm and return the response.

    Uses the AI_PROVIDER_CHAIN environment variable to determine provider(s).
    """
    global _gateway_stats
    try:
        client = _get_llm_client()
        _gateway_stats.llm_calls += 1
        return client.chat(
            messages=[{"role": "user", "content": message}],
            model=model,
        )
    except RuntimeError as e:
        _gateway_stats.llm_failures += 1
        return f"LLM error: {e}"
    except ImportError:
        _gateway_stats.llm_failures += 1
        return "LLM client not available (missing dependencies)."


@mcp.tool()
def llm_stats() -> str:
    """Get LLM call statistics for this gateway session."""
    return json.dumps(_gateway_stats.snapshot(), indent=2, ensure_ascii=False)


@mcp.tool()
def reset_llm_stats() -> str:
    """Reset gateway LLM call statistics to zero."""
    _gateway_stats.reset()
    return "Gateway LLM stats reset."


@mcp.tool()
def provider_chain() -> str:
    """Show the configured LLM provider chain."""
    chain = load_provider_chain()
    if not chain:
        return "No providers configured (check AI_PROVIDER_CHAIN)."
    lines = []
    for p in chain:
        primary = "(primary)" if p.is_primary else "(fallback)"
        lines.append(f"  {p.name} {primary}: model={p.model or 'default'}, url={p.base_url}")
    return "\n".join(lines)


def create_app() -> FastMCP:
    return mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

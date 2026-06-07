# auto_hub

Central coordination layer for the `auto_*` project family under `/Users/hainingyu/Code`.

**It is not a monorepo.** Each `auto_*` project stays in its own directory with its own Git repository. `auto_hub` provides:

- **Registry**: one place to discover what each tool does, how to run it, and what it needs.
- **Shared infrastructure**: reusable clients for LLM, HTTP, and configuration.
- **MCP aggregation**: one MCP entry point for AI agents to reach multiple tools.
- **Optional workflows**: compose tools into repeatable content production pipelines.

## Quick start

```bash
uv sync
uv run auto-hub list
uv run auto-hub show auto_pdf
```

## Phases

| Phase | Status | Description |
| --- | --- | --- |
| 0 | Skeleton | Package, CLI, Git, docs |
| 0.5 | | LLM implementation audit |
| 1 | | Project registry |
| 2 | | Shared LLM layer |
| 3 | | First migration (auto_pdf) |
| 4 | | Expand shared LLM adoption |
| 5 | | MCP aggregation |
| 6 | | Content workflow layer |

See [PLAN.md](PLAN.md) for details.

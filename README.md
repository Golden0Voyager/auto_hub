<div align="center">

# auto_hub

**Central coordination platform for the `auto_*` AI tool ecosystem**

*Unified registry, shared infrastructure, and MCP aggregation for 12+ open-source AI tools.*

[English](#overview) · [中文](README.zh-CN.md)

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/package%20manager-uv-purple.svg)](https://docs.astral.sh/uv/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-active%20development-orange.svg)](./)

</div>

---

## Table of Contents

- [Overview](#overview)
- [What auto_hub Is (and Isn't)](#what-auto_hub-is-and-isnt)
- [The auto_* Ecosystem](#the-auto_-ecosystem)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Modules](#modules)
- [Roadmap](#roadmap)
- [Contributing](#contributing)

---

## Overview

**auto_hub** is the central coordination layer for a family of 12+ open-source AI tools built under the `auto_*` umbrella. It provides a unified project registry, shared LLM infrastructure, MCP (Model Context Protocol) aggregation, and optional workflow composition — without merging any project into a monorepo.

Each `auto_*` tool remains an **independent Git repository** with its own lifecycle. `auto_hub` integrates through stable interfaces and manifests, not by physically coupling codebases.

> Think of it as a switchboard — not a merger.

---

## What auto_hub Is (and Isn't)

| auto_hub **IS** | auto_hub **IS NOT** |
|-----------------|---------------------|
| A registry to discover all `auto_*` tools | A monorepo |
| A shared LLM client to eliminate duplication | A tool rewrite engine |
| A unified MCP entry point for AI agents | A forced coupling layer |
| A workflow composer for content pipelines | A deployment platform |
| A coordination hub for humans and agents | A replacement for each tool's own CLI |

---

## The auto_* Ecosystem

| Project | Capability | Integration Stage |
|:--------|:-----------|:------------------|
| [auto_curation](https://github.com/Golden0Voyager/auto-curation) | Global art exhibition data pipeline (61 institutions) | Shared LLM chain |
| [auto_nutrition](https://github.com/Golden0Voyager/auto_nutrition) | MCP Server for AI-driven nutrition logging | Registry + MCP aggregation |
| [auto_f1](https://github.com/Golden0Voyager/auto_f1) | F1 live/historical data MCP Server | Registry + MCP aggregation |
| [auto_pdf](https://github.com/Golden0Voyager/auto_pdf) | PDF conversion, translation, AI summary | First shared LLM migration |
| [auto_html](https://github.com/Golden0Voyager/auto_html) | Markdown → HTML + AI image generation | Shared LLM/image client |
| [auto_lingo](https://github.com/Golden0Voyager/auto_lingo) | Translation, Whisper transcription, OCR | Shared LLM client |
| [auto_scrape](https://github.com/Golden0Voyager/auto_scrape) | Research scraping with AI config generation | LLM provider chain source |
| [auto_github](https://github.com/Golden0Voyager/auto_github) | GitHub trending curation | Shared LLM client |
| [auto_audiobook](https://github.com/Golden0Voyager/auto_audiobook) | TTS, voice cloning, audiobook pipeline | Registry |
| [auto_motion](https://github.com/Golden0Voyager/auto_motion) | Image/video generation | Registry |
| [auto_form](https://github.com/Golden0Voyager/auto_form) | Form generation and submission automation | Registry |
| [auto_animation](https://github.com/Golden0Voyager/auto_animation) | Animation gallery (HTML/CSS/JS) | Registry |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        auto_hub                         │
│                                                         │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────┐ │
│  │   Registry   │  │  Shared LLM    │  │     MCP     │ │
│  │              │  │ Infrastructure │  │ Aggregation │ │
│  │ • Discovery  │  │                │  │             │ │
│  │ • Manifests  │  │ • MIMO         │  │ • Unified   │ │
│  │ • Metadata   │  │ • Gemini       │  │   endpoint  │ │
│  │              │  │ • SiliconFlow  │  │ • Route to  │ │
│  │              │  │ • Fallback     │  │   any tool  │ │
│  └──────────────┘  └────────────────┘  └─────────────┘ │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Workflow Composer (Phase 6)          │   │
│  │  compose(auto_scrape → auto_curation → auto_html)│   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         │               │               │
         ▼               ▼               ▼
  auto_curation    auto_nutrition     auto_pdf
  auto_f1          auto_lingo         auto_scrape
  ...              ...                ...
```

---

## Quick Start

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Golden0Voyager/auto-hub.git
cd auto-hub
uv sync

# List all registered tools
uv run auto-hub list

# Inspect a specific tool
uv run auto-hub show auto_curation

# Run the shared LLM client
uv run auto-hub llm "Summarize this text: ..."
```

---

## Modules

| Module | Path | Description |
|:-------|:-----|:------------|
| **CLI** | `src/auto_hub/cli.py` | Entry point — `auto-hub` command |
| **Registry** | `src/auto_hub/registry/` | Tool manifest discovery and metadata |
| **LLM** | `src/auto_hub/llm/` | Shared multi-provider LLM client |
| **Document** | `src/auto_hub/document/` | Document-to-Markdown platform (MarkItDown + PyMuPDF + OCR) |
| **HTTP** | `src/auto_hub/http/` | Shared HTTP utilities |
| **Config** | `src/auto_hub/config/` | Unified configuration models |
| **MCP** | `src/auto_hub/mcp/` | MCP aggregation server |
| **Workflow** | `src/auto_hub/workflow/` | Pipeline composition layer |

### Document Platform

```python
from auto_hub.document import DocumentConverter, ConvertOptions

converter = DocumentConverter()

# Basic usage: auto-detect format and choose best extraction strategy
result = await converter.convert("path/to/file.pdf")
print(result.markdown)

# Specify OCR engine for scanned documents
result = await converter.convert(
    "path/to/scan.pdf",
    options=ConvertOptions(ocr_engine="siliconflow", language="zh"),
)
```

Supported inputs: PDF (text + scanned), DOCX, PPTX, XLSX, HTML, EPUB, CSV, TXT, Markdown, JSON, images, and more.

OCR engines: SiliconFlow DeepSeek-OCR (default), PaddleOCR (local, optional).

Optional dependency groups:

- `auto_hub[md]` — MarkItDown + PyMuPDF
- `auto_hub[ocr]` — `[md]` + OpenAI SDK (SiliconFlow OCR)
- `auto_hub[local-ocr]` — `[md]` + PaddleOCR
- `auto_hub[all]` — all engines

---

## Roadmap

| Phase | Status | Description |
|:------|:-------|:------------|
| 0 | ✅ Done | Package skeleton, CLI, Git, docs |
| 0.5 | 🔄 In Progress | LLM implementation audit across all tools |
| 1 | ⏳ Planned | Project registry — discover all tools |
| 2 | ✅ Done | Shared LLM layer — eliminate duplication |
| 3 | ✅ Done | First migration: `auto_pdf` / `auto_lingo` → Document platform |
| 4 | ⏳ Planned | Expand shared LLM to all tools |
| 5 | ⏳ Planned | MCP aggregation — one endpoint for all |
| 6 | ⏳ Planned | Content workflow composition layer |

See [PLAN.md](PLAN.md) for full technical specifications.

---

## Contributing

`auto_hub` follows the same conventions as all `auto_*` projects:

- Package management: `uv`
- Code style: `ruff` + `mypy`
- Type hints required (PEP 484)
- Surgical changes only — no cross-project refactoring without explicit request
- Commit messages: bilingual (English first, Chinese second)

```bash
uv sync
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

---

## License

[MIT License](LICENSE) © 2026 auto_hub Contributors

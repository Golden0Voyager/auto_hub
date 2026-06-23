<div align="center">

# auto_hub · 自动化工具协调中枢

**`auto_*` AI 工具生态系的中央协调平台**

*统一注册表、共享基础设施与 MCP 聚合——覆盖 12+ 个开源 AI 工具。*

[English](README.md) · [中文](#概述)

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/package%20manager-uv-purple.svg)](https://docs.astral.sh/uv/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-积极开发中-orange.svg)](./)

</div>

---

## 目录

- [概述](#概述)
- [auto_hub 是什么（以及不是什么）](#auto_hub-是什么以及不是什么)
- [auto_* 生态系全景](#auto_-生态系全景)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [模块说明](#模块说明)
- [开发路线图](#开发路线图)
- [贡献指南](#贡献指南)

---

## 概述

**auto_hub** 是 `auto_*` 家族 12+ 个开源 AI 工具的中央协调层。它提供统一项目注册表、共享 LLM 基础设施、MCP（模型上下文协议）聚合，以及可选的工作流组合能力——且**不**将任何项目合并为 monorepo。

每个 `auto_*` 工具保持独立的 Git 仓库和自己的生命周期。`auto_hub` 通过稳定接口和 Manifest 文件进行集成，而非物理耦合各代码库。

> 把它理解为一个**交换机**——而非合并器。

---

## auto_hub 是什么（以及不是什么）

| auto_hub **是** | auto_hub **不是** |
|----------------|------------------|
| 发现所有 `auto_*` 工具的注册表 | Monorepo |
| 消除重复的共享 LLM 客户端 | 工具重写引擎 |
| AI 客户端的统一 MCP 入口 | 强制耦合层 |
| 内容生产流水线的工作流组合器 | 部署平台 |
| 人与 AI 代理的协调中枢 | 替代各工具自己的 CLI |

---

## auto_* 生态系全景

| 项目 | 核心能力 | 集成阶段 |
|:-----|:---------|:---------|
| [auto_curation](https://github.com/Golden0Voyager/auto-curation) | 全球艺术展览数据管道（61 家机构）| 共享 LLM 链 |
| [auto_nutrition](https://github.com/Golden0Voyager/auto_nutrition) | AI 驱动营养记录 MCP Server | 注册表 + MCP 聚合 |
| [auto_f1](https://github.com/Golden0Voyager/auto_f1) | F1 实时/历史数据 MCP Server | 注册表 + MCP 聚合 |
| [auto_pdf](https://github.com/Golden0Voyager/auto_pdf) | PDF 转换、翻译、AI 摘要 | 首个共享 LLM 迁移 |
| [auto_html](https://github.com/Golden0Voyager/auto_html) | Markdown → HTML + AI 图像生成 | 共享 LLM/图像客户端 |
| [auto_lingo](https://github.com/Golden0Voyager/auto_lingo) | 翻译、Whisper 转录、OCR | 共享 LLM 客户端 |
| [auto_scrape](https://github.com/Golden0Voyager/auto_scrape) | AI 配置生成的研究爬虫 | LLM provider 链来源 |
| [auto_github](https://github.com/Golden0Voyager/auto_github) | GitHub 趋势内容策展 | 共享 LLM 客户端 |
| [auto_audiobook](https://github.com/Golden0Voyager/auto_audiobook) | TTS、声音克隆、有声书流水线 | 注册表 |
| [auto_motion](https://github.com/Golden0Voyager/auto_motion) | 图像/视频生成 | 注册表 |
| [auto_form](https://github.com/Golden0Voyager/auto_form) | 表单生成与提交自动化 | 注册表 |
| [auto_animation](https://github.com/Golden0Voyager/auto_animation) | 动画画廊（HTML/CSS/JS）| 注册表 |

---

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                        auto_hub                         │
│                                                         │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────┐ │
│  │    注册表    │  │   共享 LLM     │  │  MCP 聚合   │ │
│  │              │  │   基础设施     │  │             │ │
│  │ • 发现工具   │  │                │  │ • 统一入口  │ │
│  │ • Manifests  │  │ • MIMO         │  │ • 路由至任  │ │
│  │ • 元数据     │  │ • Gemini       │  │   意工具    │ │
│  │              │  │ • SiliconFlow  │  │             │ │
│  │              │  │ • 回退链       │  │             │ │
│  └──────────────┘  └────────────────┘  └─────────────┘ │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │             工作流组合器（Phase 6）               │   │
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

## 快速开始

需要 Python ≥ 3.12 与 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/Golden0Voyager/auto-hub.git
cd auto-hub
uv sync

# 列出所有已注册工具
uv run auto-hub list

# 查看某个工具的详细信息
uv run auto-hub show auto_curation

# 使用共享 LLM 客户端
uv run auto-hub llm "请总结这段文字：..."
```

---

## 模块说明

| 模块 | 路径 | 说明 |
|:-----|:-----|:-----|
| **CLI** | `src/auto_hub/cli.py` | 入口点——`auto-hub` 命令 |
| **Registry** | `src/auto_hub/registry/` | 工具 Manifest 发现与元数据管理 |
| **LLM** | `src/auto_hub/llm/` | 共享多供应商 LLM 客户端 |
| **Document** | `src/auto_hub/document/` | 文档转 Markdown 中台（MarkItDown + PyMuPDF + OCR） |
| **HTTP** | `src/auto_hub/http/` | 共享 HTTP 工具库 |
| **Config** | `src/auto_hub/config/` | 统一配置模型 |
| **MCP** | `src/auto_hub/mcp/` | MCP 聚合服务器 |
| **Workflow** | `src/auto_hub/workflow/` | 流水线组合层 |

### Document 中台

```python
from auto_hub.document import DocumentConverter, ConvertOptions

converter = DocumentConverter()

# 基础用法：自动识别格式并选择最佳提取策略
result = await converter.convert("path/to/file.pdf")
print(result.markdown)

# 指定 OCR 引擎处理扫描件
result = await converter.convert(
    "path/to/scan.pdf",
    options=ConvertOptions(ocr_engine="siliconflow", language="zh"),
)
```

支持的输入格式：PDF（文本型 + 扫描型）、DOCX、PPTX、XLSX、HTML、EPUB、CSV、TXT、Markdown、JSON、图片等。

OCR 引擎：SiliconFlow DeepSeek-OCR（默认）、PaddleOCR（本地，可选）。

可选依赖分组：

- `auto_hub[md]` — MarkItDown + PyMuPDF
- `auto_hub[ocr]` — `[md]` + OpenAI SDK（SiliconFlow OCR）
- `auto_hub[local-ocr]` — `[md]` + PaddleOCR
- `auto_hub[all]` — 全部引擎

---

## 开发路线图

| 阶段 | 状态 | 说明 |
|:-----|:-----|:-----|
| 0 | ✅ 完成 | 包骨架、CLI、Git、文档 |
| 0.5 | 🔄 进行中 | 全工具 LLM 实现审计 |
| 1 | ⏳ 计划中 | 项目注册表——发现所有工具 |
| 2 | ✅ 完成 | 共享 LLM 层——消除重复实现 |
| 3 | ✅ 完成 | 首次迁移：`auto_pdf` / `auto_lingo` → Document 中台 |
| 4 | ⏳ 计划中 | 向所有工具扩展共享 LLM |
| 5 | ⏳ 计划中 | MCP 聚合——一个入口覆盖所有工具 |
| 6 | ⏳ 计划中 | 内容工作流组合层 |

完整技术规格详见 [PLAN.md](PLAN.md)。

---

## 贡献指南

`auto_hub` 遵循所有 `auto_*` 项目的统一规范：

- 包管理：`uv`
- 代码风格：`ruff` + `mypy`
- 强制使用 Type Hints（PEP 484）
- 外科手术式修改——未经明确要求不跨项目重构
- Commit message：中英双语（英文在前，中文在后）

```bash
uv sync
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```

---

## 许可证

[MIT License](LICENSE) © 2026 auto_hub Contributors

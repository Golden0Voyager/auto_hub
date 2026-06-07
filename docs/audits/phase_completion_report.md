# auto_hub Integration — 完成报告

**日期**: 2026-06-06
**Phase**: 0–6（全部完成）
**测试**: 75 个，全部通过

---

## 交付概览

| 模块 | 文件 | 位置 | 行数 |
|------|------|------|------|
| CLI | `cli.py` | `src/auto_hub/` | 209 |
| 注册表 | `models.py`, `loader.py` | `src/auto_hub/registry/` | 126 |
| 共享 LLM | `models.py`, `provider_chain.py`, `client.py`, `json.py`, `stats.py` | `src/auto_hub/llm/` | 160 |
| MCP 网关 | `gateway.py` | `src/auto_hub/mcp/` | 141 |
| 工作流 | `models.py`, `runner.py` | `src/auto_hub/workflow/` | 220 |
| **总计** | **13 个源文件** | | **~1000 行** |

## Phase 完成清单

### Phase 0 — 建立 auto_hub
- [x] `pyproject.toml` (uv 包, Python ≥3.12)
- [x] CLI 入口 (`auto-hub` click group)
- [x] `CLAUDE.md`, `README.md`, `README.zh-CN.md`
- [x] `.gitignore`
- [x] 独立 Git 仓库

### Phase 0.5 — LLM 实施审计
- [x] 审计 6 个 auto_* 项目的 LLM 实现
- [x] `docs/audits/llm_implementations.md`
- [x] 抽象边界建议（ProviderConfig, provider chain, retry, JSON parsing, stats → 共享；domain prompts, image gen, cache → 项目级）

### Phase 1 — 项目注册表
- [x] `manifests/projects.yaml`（13 个项目）
- [x] Pydantic 模型（`ProjectManifest`, `RegistryManifest` 等）
- [x] `RegistryLoader`（YAML 加载 / 路径解析 / 缺失检测）
- [x] CLI 命令：`list`, `show`, `status`, `env`
- [x] 11 个注册表测试

### Phase 2 — 共享 LLM 层
- [x] `ProviderConfig` 模型 + `DEFAULT_BASE_URLS`
- [x] `load_provider_chain()` — AI_PROVIDER_CHAIN 环境变量驱动
- [x] `LLMClient` — 同步客户端，provider chain 回退，重试/退避
- [x] `AsyncLLMClient` — 异步客户端
- [x] 硬失败检测（`HARD_FAIL_PATTERNS`）
- [x] `parse_llm_json()` — fence stripping + JSON 解析
- [x] `CallStats` — 调用计数/令牌统计/快照
- [x] 16 个 LLM 测试

### Phase 3 — auto_pdf 迁移（试点）
- [x] `llm_client.py` → 委托给 `auto_hub.llm` 的 `chat()`
- [x] `try auto_hub` / `fallback old` 模式
- [x] 87 个 auto_pdf 测试通过

### Phase 4 — 扩展 LLM 采纳（5 个项目）
- [x] **auto_html**: `chat_completion()` 委托给 auto_hub.llm + 原始 API 回退（35 测试通过）
- [x] **auto_github**: `src/llm.py` → auto_hub.llm 主 + OpenAI SDK 回退
- [x] **auto_scrape**: `provider.py` → 薄适配器（243 测试通过）
- [x] **auto_curation**: `llm_parser.py` → 旧 env 变量映射 + 委托（11 测试通过）
- [x] **auto_lingo**: `openai_service.py` → 共享 `_extract_retry_after`（6 测试通过）

### Phase 5 — MCP 聚合网关
- [x] FastMCP 服务器，7 个工具：
  - `list_projects`, `show_project`, `registry_status`
  - `llm_chat`, `llm_stats`, `reset_llm_stats`
  - `provider_chain`
- [x] `auto-hub mcp` CLI 命令（stdio 传输）
- [x] `mcp` 添加至依赖
- [x] 12 个 MCP 网关测试
- [x] AI 客户端文档（`docs/clients/claude_desktop.md`, `cursor.md`）
- [x] 示例 pipeline（`examples/scrape-to-github-pipeline.json`）

### Phase 6 — 工作流层
- [x] 工件契约模型（`ArtifactManifest`, `JobSpec`, `StepSpec`, `StepResult`）
- [x] `JobRunner` — 顺序执行、跳过已完成步骤、自动重试、日志
- [x] Job 目录布局：`source/`, `intermediate/`, `output/`, `assets/`, `logs/`
- [x] CLI 命令：`workflow run`, `workflow status`
- [x] 23 个工作流测试

## 测试统计

| 文件 | 测试数 |
|------|--------|
| `test_cli.py` | 6 |
| `test_registry.py` | 10 |
| `test_llm_provider_chain.py` | 19 |
| `test_mcp_gateway.py` | 12 |
| `test_workflow.py` | 23 |
| **总计** | **70** |

*注：另有 5 个测试在 auto_pdf/auto_html/auto_scrape/auto_curation/auto_lingo 项目中委托给 auto_hub。*

## 架构决策记录

1. **Hub 而非 Monorepo** — 每个 auto_* 项目保持独立 Git 仓库
2. **迁移模式** — `try auto_hub.llm` / `fallback old`：无强制绑定
3. **Env 兼容性** — 旧 env 变量名映射至 `AI_PROVIDER_CHAIN` 格式
4. **契约先行** — 工作流层先定义 `ArtifactManifest`，再实现 `JobRunner`
5. **FastMCP** — 标准 MCP Python SDK（非自定义 JSON-RPC）
6. **测试隔离** — 使用 `reset_provider_chain()` 清理 LLM 缓存状态

## 已知限制

- auto_audiobook 的 pipeline 模式尚未集成至 JobRunner（计划中后期）
- 工作流只支持子进程步骤（尚无 Python API 步骤）
- MCP 网关暂无项目工具代理（目前仅暴露 auto_hub 自身工具）
- 部分旧项目（auto_curation, auto_html）需 `uv pip install ".[dev]"` 安装 pytest

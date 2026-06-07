# AGENTS.md — auto_hub

auto_hub 是 auto_* 项目的中心协调层。它不是 monorepo。

## 环境约束（强制）

- 包管理器：`uv sync` / `uv pip install`，禁止 `pip`
- 运行脚本：`uv run auto-hub ...`，禁止直接 `python`
- Python ≥ 3.12

## 本地规则

- 使用 `src/auto_hub` 包布局
- Python 模块、YAML key、capability ID 使用蛇形命名（snake_case）
- CLI 命令使用短横线命名（kebab-case）：`auto-hub list`、`auto-hub show`
- 不做读/修改 `.env`、`secrets.json`、`cookies.json`
- 默认测试必须离线、不依赖 API key
- Registry 加载时不导入兄弟 `auto_*` 项目的代码
- Manifest 和配置边界优先使用 Pydantic 模型
- 适配器要薄，领域 prompt 和业务逻辑留在原项目中

## 常用命令

```bash
uv sync                          # 安装依赖
uv run auto-hub --help           # CLI 帮助
uv run auto-hub list             # 列出所有项目
uv run auto-hub show auto_pdf    # 查看单个项目
uv run pytest                    # 运行测试
uv run pytest tests/ -v          # 详细测试
uv run ruff check src/ tests/    # Lint
```

## 项目结构

```
auto_hub/
  pyproject.toml
  AGENTS.md
  README.md / README.zh-CN.md
  manifests/
    projects.yaml         # 13 个 auto_* 项目的注册表
  src/auto_hub/
    cli.py                # CLI 入口
    registry/
      models.py           # Pydantic 模型
      loader.py           # YAML 加载/验证
    llm/                  # Phase 2: 共享 LLM 层
    config/               # 环境变量配置
    http/                 # HTTP 重试工具
    mcp/                  # Phase 5: MCP 聚合
  tests/
  docs/
    audits/               # LLM 实现审计报告
    clients/              # AI 客户端配置文档
```

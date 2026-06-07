# auto_hub

`auto_*` 项目家族的中央协调层。

**它不是 monorepo。** 每个 `auto_*` 项目保持独立的目录和 Git 仓库。`auto_hub` 提供：

- **注册表**：统一发现每个工具的功能、运行方式和依赖
- **共享基础设施**：LLM 客户端、HTTP 工具、配置模型等可复用组件
- **MCP 聚合**：一个统一的 MCP 入口，让 AI 客户端可以访问多个工具
- **可选工作流**：将多个工具组合成可重复的内容生产流水线

## 快速开始

```bash
uv sync
uv run auto-hub list
uv run auto-hub show auto_pdf
```

## 阶段

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| 0 | 进行中 | 骨架：包、CLI、Git、文档 |
| 0.5 | | LLM 实现审计 |
| 1 | | 项目注册表 |
| 2 | | 共享 LLM 层 |
| 3 | | 首次迁移（auto_pdf） |
| 4 | | 扩展 LLM 共享 |
| 5 | | MCP 聚合 |
| 6 | | 内容工作流层 |

详见 [PLAN.md](PLAN.md)。

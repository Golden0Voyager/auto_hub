# CLAUDE.md — auto_hub

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
  CLAUDE.md
  README.md / README.zh-CN.md
  manifests/
    projects.yaml         # 13 个 auto_* 项目的注册表
  src/auto_hub/
    cli.py                # CLI 入口
    registry/
      models.py           # Pydantic 模型
      loader.py           # YAML 加载/验证
    llm/                  # Phase 2: 共享 LLM 层
    document/             # 文档转 Markdown 中台
      converter.py        # DocumentConverter 统一入口
      models.py           # ConvertOptions / ConversionResult / OCRResult
      extractors/         # MarkItDownExtractor / PyMuPDFExtractor
      ocr/                # OCR 引擎注册表与 SiliconFlow 引擎
      exceptions.py       # DocumentConversionError 等异常
    config/               # 环境变量配置
    http/                 # HTTP 重试工具
    mcp/                  # Phase 5: MCP 聚合
  tests/
  docs/
    audits/               # LLM 实现审计报告
    clients/              # AI 客户端配置文档
```

## Document 中台

`auto_hub.document` 是 auto_* 家族共享的文档 → Markdown 转换平台。

```python
from auto_hub.document import DocumentConverter, ConvertOptions

converter = DocumentConverter()
result = await converter.convert("path/to/file.pdf")
print(result.markdown)

# 扫描件指定 OCR 引擎
result = await converter.convert(
    "path/to/scan.pdf",
    options=ConvertOptions(ocr_engine="siliconflow", language="zh"),
)
```

### 关键设计

- **统一入口**：`DocumentConverter.convert(file_path, options=None)` 自动根据扩展名选择提取策略。
- **Extractor 链**：`MarkItDownExtractor` 覆盖多格式；`PyMuPDFExtractor` 处理文本型 PDF。
- **OCR 引擎注册表**：`BaseOCREngine` + `@register_engine` + `OCRRegistry`，默认提供 SiliconFlow DeepSeek-OCR。
- **懒加载依赖**：缺少可选依赖时抛出中文异常并附带 `suggestion`（如 `uv pip install 'auto_hub[ocr]'`）。
- **可选依赖分组**：
  - `auto_hub[md]` — MarkItDown + PyMuPDF
  - `auto_hub[ocr]` — `[md]` + OpenAI SDK（SiliconFlow OCR）
  - `auto_hub[local-ocr]` — `[md]` + PaddleOCR
  - `auto_hub[all]` — 全部引擎

### 新增/修改文件时的约束

- 所有 extractor 必须继承 `BaseExtractor`，实现 `can_handle(path)` 和 `extract(path, options)`。
- 所有 OCR 引擎必须继承 `BaseOCREngine`，设置 `name` 类属性，并用 `@register_engine` 注册。
- 引擎注册 side-effect 统一在 `auto_hub/document/__init__.py` 中触发，不要放到 `converter.py`。
- 用户可见错误信息使用中文，包含可执行的 `suggestion`。
- 默认测试必须离线；涉及 API 调用的 OCR 测试使用 `pytest-mock` 或 monkeypatch。

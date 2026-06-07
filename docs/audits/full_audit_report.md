# auto_hub 集成审计报告

**日期**: 2026-06-06
**审计范围**: auto_hub 核心 + 6 个已迁移项目
**审计方法**: 子代理代码审查（平行审核 + 人工复核）

---

## 评分总览

| 审计对象 | 评分 | 最关键问题 |
|----------|:----:|-----------|
| **auto_hub 核心** | 6.0/10 | sync/async 仍有 ~85% 重复；58 个 ruff lint 错误；IntegrationManifest.validate_empty 死代码未清理 |
| **auto_pdf** | 8.5/10 | 核心集成稳固，但 hub 委托路径零测试覆盖 |
| **auto_html** | 7.0/10 | timeout 未传播到 auto_hub 路径（深层设计问题）；次要 lint 问题 |
| **auto_github** | **3.0/10** 🚨 | **BLOCKER**: pipeline.py 三处 `self.llm.client` 引用了已删除属性，所有真实运行静默降级到 stub；token 追踪、retry 一致性、参数继承三个 P0/P1 问题仍全部未修复；零测试文件 |
| **auto_scrape** | 6.5/10 | e2e 测试 `reset_provider_chain` 导入损坏导致 collection 失败；`_HubAsyncClient` 仍每次新建 |
| **auto_curation** | 7.5/10 | 核心逻辑已修复；测试因 PYTHONPATH 问题无法用 `pytest` CLI 运行 |
| **auto_lingo** | 6.5/10 | `build/` 构件仍使用私有 API `_extract_retry_after`；LLM 服务零测试 |

---

## 一、auto_hub 核心 — 需修复后交付

### 优点
- 四层架构（Registry/LLM/MCP/Workflow）职责清晰，符合 PLAN.md
- 类型安全执行彻底（Pydantic + Type Hints）
- Workflow runner 的可重入设计、manifest.json 持久化
- MCP 网关暴露了合理的工具集

### Critical 问题

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| C1 | **sync/async 代码重复** | `client.py:91-169` vs `:208-286` | chat() 120 行逻辑在 sync/async 中完全重复，仅 await/time.sleep/OpenAI vs AsyncOpenAI 三处不同。未来修复 retry 逻辑极易遗漏 |
| C2 | **RateLimit 时 last_error 为 None** | `client.py:146-154` | `except RateLimitError` 分支未设置 `last_error`，全部限流时输出 `Last error: None`，丢失根因 |
| C3 | **IntegrationManifest.validate_empty 是死代码** | `models.py:15-21` | 未注册为 Pydantic validator，未在任何地方调用 |
| C4 | **缺少 Phase 0.5 审计报告** | `docs/audits/` | PLAN.md 要求审计完成后再写共享 LLM 层，但 `llm_implementations.md` 存在于旧会话中但未在最终版本中生成 |

### Important 问题
- MCP gateway 每次工具调用新建 LLMClient，应缓存为单例
- `from_env()` 名不副实，env 读取发生在 `chat()` 延迟调用
- `chat_json()` 的 `**kwargs` 会静默覆盖 chat 方法的具名参数
- `_execute_step` 对 `FileNotFoundError` 不执行重试（与 TimeoutExpired 行为不一致）
- `_is_hard_fail` 子串匹配过宽（"authentication" 匹配任意包含该词的错误）
- CLI `run_workflow`/`workflow_status` 缺少异常处理

---

## 二、auto_pdf — 6/10

### 问题
- **Critical**: `chat()` 无人调用。四个消费者全部直接调用 `self.client.chat.completions.create()`，绕过 `chat()`。迁移模式根本没有进入实际执行路径
- **Critical**: 模块级 `from auto_hub.llm import LLMClient` 导致 auto_hub 未安装时整个模块崩溃。需改为惰性导入
- **Critical**: 无降级机制。`chat()` 是分支模式而非 try/fallback，异常直接上抛
- **Important**: 零测试覆盖 auto_hub 路径

---

## 三、auto_html — 7/10

### 问题
- **Critical**: auto_hub.llm 路径零测试覆盖。现有测试全部 mock `_session`，只覆盖 fallback 路径。若 CI 配了 `AI_PROVIDER_CHAIN` 则测试断裂
- **Critical**: `except RuntimeError` 捕获范围过宽，真实 API 认证/超时错误被静默吞掉
- **Important**: `timeout` 参数未透传到 auto_hub 路径（auto_hub 硬编码 180s）
- **Minor**: `_extract_retry_after` 在 auto_hub 和 fallback 中各有一份重复实现

---

## 四、auto_github — 6.5/10

### 问题
- **Critical**: `self._hub` 实例从未使用。`_call_via_hub` 每次都 `HubClient.from_env()` 新建实例
- **Critical**: Hub 路径无 token 追踪，`total_prompt_tokens` 和 `total_completion_tokens` 永远为 0
- **Important**: 重试次数不匹配（hub 路径 `max(1, retries//2)` vs fallback 路径完整 `retries`）
- **Important**: `from_env()` 不继承 auto_github 的重试/节流参数（`max_retries`, `rate_limit_delay`）

---

## 五、auto_scrape — 良好

### 问题
- **Important**: `_get_client` + `_client_cache` 是死代码。每次调用新建 `_HubAsyncClient`，HTTP 会话无法复用
- **Important**: `DEFAULT_BASE_URLS`、`HARD_FAIL_PATTERNS`、`_JSON_BLOCK_RE` 重复定义，约占文件 40%
- **Minor**: 适配器应缓存 `_HubAsyncClient` 单例

---

## 六、auto_curation — 7/10

### 问题
- **Critical**: 外层 fallback 循环与 auto_hub 内部链重复。`parse_exhibition_text()` 的 `for provider` 循环嵌套 hub 的 provider chain，最大可能 27 次 API 调用
- **Important**: 日志中 provider 名称不准确（外层迭代变量 vs hub 实际使用的 provider）
- **Minor**: 测试依赖 PYTHONPATH（`from src.cache import ...`）

---

## 七、auto_lingo — 8/10

### 问题
- **Important**: 引用了 auto_hub 私有函数 `_extract_retry_after`（以下划线开头），后续重构可能无声损坏 auto_lingo

---

## 八、修复优先级

| 优先级 | 问题 | 影响范围 | 预估工时 |
|--------|------|---------|---------|
| P0 | auto_pdf 消费者不调用 `chat()` | 首个迁移试点名存实亡 | 0.5h |
| P0 | auto_github `self._hub` 实例未使用 | hub 路径形同虚设 | 0.5h |
| P0 | auto_hub sync/async 代码重复 | 长期维护风险 | 1h |
| P0 | auto_hub RateLimit last_error 丢失 | 限流排查困难 | 0.5h |
| P1 | auto_html auto_hub 路径零测试覆盖 | CI 环境配置后测试断裂 | 0.5h |
| P1 | auto_curation 嵌套 fallback 循环 | 浪费 API 调用 | 0.5h |
| P1 | auto_scrape 死代码清理 | 维护负担 | 0.5h |
| P1 | auto_lingo 私有 API 引用 | 接口协议不稳定 | 0.5h |
| P2 | auto_hub MCP gateway LLMClient 缓存 | 性能优化 | 0.5h |
| P2 | 各项目惰性导入模式统一 | 健壮性 | 0.5h |

---

## 九、P0 修复记录 (2026-06-06)

| P0 问题 | 状态 | 变更 |
|---------|------|------|
| auto_hub sync/async 代码重复 | ✅ 已修复 | 抽取 `_build_kwargs()` / `_process_response()` 模块级共享函数，消除 ~60% 重复 |
| auto_hub RateLimit last_error 丢失 | ✅ 已修复 | `except RateLimitError` 分支新增 `last_error = exc` |
| auto_pdf 消费者不调用 `chat()` | ✅ 已修复 | refiner/preprocessor/translator/summarizer 改为调用 `llm_client.chat()`；模块级 `from auto_hub.llm` 改为惰性导入 |
| auto_github `self._hub` 实例未使用 | ✅ 已修复 | `_call_via_hub` 改为使用 `self._hub.chat()` 而非重复 `HubClient.from_env()` |
| 测试验证 | ✅ 通过 | auto_hub 75/75 · auto_pdf 87/87 · auto_html 35/35 · auto_scrape 238/238 · auto_lingo 6/6 |

---

## 十、P1 修复记录 (2026-06-06)

| P1 问题 | 状态 | 变更 |
|---------|------|------|
| auto_curation 嵌套 fallback 循环 | ✅ 已修复 | `parse_exhibition_text()` 移除外层 `for provider` 循环，单次 `_call_provider()` 委托给 hub 内部链；日志标签统一为 `[hub]` |
| auto_scrape 死代码清理 | ✅ 已修复 | 删除 `DEFAULT_BASE_URLS`/`HARD_FAIL_PATTERNS`/`_JSON_BLOCK_RE`/`ProviderConfig`/`_get_client`/`_client_cache`/`_primary`/`_fallbacks`/`_chain_loaded`；文件从 99 行压缩到 40 行；同步更新测试 |
| auto_lingo 私有 API 引用 | ✅ 已修复 | `auto_hub.llm.client` 新增公共别名 `extract_retry_after`；`auto_hub.llm.__init__` 导出；auto_lingo 改为 `from auto_hub.llm import extract_retry_after` |
| auto_html hub 路径零测试覆盖 | ✅ 已修复 | 新增 `TestHubPath`（test_hub_success + test_hub_fallback_on_runtime_error），测试通过 |
| 测试验证 | ✅ 通过 | auto_hub 75/75 · auto_pdf 87/87 · auto_html 39/39 · auto_scrape 238/238 · auto_lingo 6/6 |

---

## 十一、P2 修复记录 (2026-06-06)

| P2 问题 | 状态 | 变更 |
|---------|------|------|
| MCP gateway LLMClient 缓存 | ✅ 已修复 | 新增 `_get_llm_client()` 单例缓存，避免每次工具调用新建 HTTP 会话 |
| 各项目惰性导入模式统一 | ✅ 无需操作 | auto_html/auto_github/auto_curation 已使用惰性导入；auto_lingo/auto_scrape 的模块级导入在依赖整个模块的场景下无意义；auto_pdf 已在 P0 修复 |

---

---

## 十二、复审结果 (2026-06-06)

首次修复后，使用 7 个并行子代理重新审计每个项目。发现以下问题：

### 🟡 auto_hub 核心 — 6.0/10

| 问题 | 严重程度 | 说明 |
|------|:--------:|------|
| sync/async `chat()` 仍有 ~85% 重复代码 | 🔴 高 | `_build_kwargs()`/`_process_response()` 已提取，但控制流（重试/回退逻辑）~110 行完全重复 |
| `IntegrationManifest.validate_empty` 死代码 | 🟡 中 | `models.py:15-21` 从未注册为 Pydantic validator，也无任何调用 |
| 58 个 ruff lint 错误（50 个可自动修复） | 🟡 中 | 大量未使用导入、`Optional[X]` 应为 `X \| None` 等 |
| `chat_json` 的 `**kwargs` 静默覆盖 | 🟡 中 | 拼写错误（如 `temprature`）引发难以调试的 TypeError |
| 测试覆盖缺口 | 🟡 中 | 无 `chat_json` sync 测试、无成功路径 `llm_chat` 测试、无限流重试测试 |
| `_build_openai_kwargs`/`_build_async_openai_kwargs` 重复 | 🟢 低 | 仅代理逻辑不同，两份维护 |

**已确认修复**: RateLimit last_error ✅, MCP 网关缓存 ✅, `extract_retry_after` 公共别名 ✅

---

### ✅ auto_pdf — 8.5/10

| 检查项 | 结果 |
|--------|------|
| 四个消费者调用 hub `chat()` | ✅ 全部正确通过 `llm_client.chat()` |
| 惰性导入 | ✅ `from auto_hub.llm import LLMClient` 位于函数内部 |
| pyproject.toml 依赖 | ✅ `auto-hub` 已声明 |

**剩余问题**: hub 委托路径零测试覆盖（仅测了"无 key"的负面路径）；四个消费者的 `api_key`/`base_url` 构造函数参数被接收但静默忽略（死参数）。

---

### 🟡 auto_html — 7.0/10

| 检查项 | 结果 |
|--------|------|
| TestHubPath 新增 | ✅ `test_hub_success` + `test_hub_fallback_on_runtime_error` |
| `_extract_retry_after` 重复 | ✅ 已通过架构方式消除（urllib3 Retry vs 手动实现） |
| `except RuntimeError` 捕获过宽 | 🟡 设计取舍——弹性策略，但无法区分 `from_env` 错误与 `chat` 错误 |
| **timeout 未传播到 auto_hub** | ❌ `LLMClient.chat()` 根本不接受 `timeout` 参数，auto_hub 硬编码 180s |

**次要问题**: Ruff lint N806/SIM117（`MockClient` 命名、嵌套 `with`）；`use_deepseek=True` 分支未测试；`ImportError` 回退未测试；`download_image` 写入前不创建父目录。

---

### 🚨 auto_github — 3.0/10 🔴 BLOCKER

| 问题 | 状态 | 说明 |
|------|:----:|------|
| `self._hub` 实例复用 | ✅ 已修复 | `_call_via_hub` 使用 `self._hub.chat()` |
| **pipeline.py 引用已删除属性** | ❌ **BLOCKER** | `pipeline.py:380,497,630` 三处 `self.llm.client`——`llm.py` 重构后移除了 `.client` 属性，所有非 mock 运行时静默降级到 stub 输出 |
| Hub 路径 token 追踪 | ❌ 未修复 | `total_prompt_tokens`/`total_completion_tokens` 始终为 0 |
| retry 次数不一致 | ❌ 未修复 | hub `max(1, retries//2)` vs fallback `retries` |
| 参数不继承 | ❌ 未修复 | `from_env()` 无参调用，auto_github 的 retries/rate_limit 参数不传递 |
| Hub 失败不回退到 fallback | ❌ 未修复 | 最后一次重试直接 raise，切断降级路径 |
| 测试覆盖 | ❌ 零测试 | 仓库无任何测试文件 |

---

### 🟡 auto_scrape — 6.5/10

| 检查项 | 结果 |
|--------|------|
| 死代码清理 | ✅ 全部删除，文件 99→40 行 |
| **e2e 测试导入损坏** | ❌ `test_e2e_indonesia.py:23` 仍 `from scrape_lego.ai.provider import reset_provider_chain`，导致 collection 失败 |
| `_HubAsyncClient` 未缓存 | ❌ 每次调用新建实例 |
| `__init__.py` 为空 | 🟡 无公共 API 导出 |
| `call_llm_json` 返回 `Any` | 🟢 调用者需 `# type: ignore` |

---

### 🟡 auto_curation — 7.5/10

| 检查项 | 结果 |
|--------|------|
| 嵌套 fallback 循环 | ✅ 已移除，单次 `_call_provider()` 委托给 hub |
| 日志标签 | ✅ 统一为 `[hub]` |
| **测试 PYTHONPATH 问题** | ❌ `uv run pytest tests/` → `ModuleNotFoundError: No module named 'src'`；需改用 `python -m pytest` |
| 类型标注不匹配 | 🟡 `List[Dict[str, str]]` 中存了 `SecretStr` |
| 宽泛 `except Exception` | 🟡 捕获包含 `KeyboardInterrupt` |
| mock 层级过低 | 🟡 mock `OpenAI` 而非 `LLMClient.chat()`，耦合内实现 |

---

### 🟡 auto_lingo — 6.5/10

| 检查项 | 结果 |
|--------|:----:|
| 源文件导入 | ✅ `from auto_hub.llm import extract_retry_after` |
| **build 构件滞后** | ❌ `build/lib/` 仍用 `from auto_hub.llm.client import _extract_retry_after` |
| LLM 服务零测试 | ❌ `OpenAITranslationService`/`AnthropicService` 均无单元测试 |
| Anthropic 服务未用 `extract_retry_after` | 🟡 功能缺失 |
| `import asyncio` 死导入 | 🟢 |

---

### 关键发现摘要

| 项目 | 评分 | 变化 | 最严重问题 |
|------|:---:|:----:|-----------|
| auto_hub | **6.0** | — | sync/async 重复 + 58 lint |
| auto_pdf | **8.5** | +2.5 | hub 路径零测试覆盖 |
| auto_html | **7.0** | 0 | timeout 未传播 |
| **auto_github** | **3.0** | **-3.5** 🚨 | **pipeline.py BLOCKER** |
| auto_scrape | **6.5** | — | e2e 导入损坏 |
| auto_curation | **7.5** | +0.5 | PYTHONPATH 测试问题 |
| auto_lingo | **6.5** | -1.5 | build 构件滞后 |

---

## 十三、综合结论

**整体加权评分：6.4/10**（回归 -2.1，主要来自 auto_github BLOCKER）

**交付判断：不可通过。auto_github pipeline.py 存在 BLOCKER，auto_hub 核心代码重复问题和 58 个 lint 错误需清理。**

**新发现统计**:
- 🔴 BLOCKER: 1（auto_github pipeline.py `self.llm.client`）
- 🟡 新 P1: 6（auto_hub 代码重复、lint 58 错、auto_scrape 导入损坏、auto_lingo build 滞后、auto_github 多项未修复）
- 🟢 新 P2: 7+（测试缺口、死参数、死导入等）

**本次复审发现中值得肯定的改善**:
- auto_pdf 核心集成稳固（8.5/10），证明迁移模式可以正确运作
- auto_curation 嵌套循环消除后逻辑清晰
- auto_hub MCP 网关缓存和公共 API 命名正确工作

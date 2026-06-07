# LLM Implementation Audit

Date: 2026-06-05
Objective: Compare existing LLM implementations to design the shared `auto_hub.llm` abstraction.

## Audit Table

| Column | auto_scrape | auto_github | auto_pdf | auto_html | auto_lingo | auto_curation |
|---|---|---|---|---|---|---|
| **File** | `src/scrape_lego/ai/provider.py` | `src/llm.py` | `llm_client.py` | `src/md_to_html/sensenova_client.py` | `services/openai_service.py` | `src/llm_parser.py` |
| **File exists** | ✅ 285 lines | ✅ 144 lines | ✅ 74 lines | ✅ 196 lines | ✅ 199 lines | ✅ 404 lines |
| **Public surface** | `call_llm()`, `call_llm_json()`, `load_provider_chain()` | `LLMClient.call_llm()`, `.get_stats()`, `.reset_stats()` | `create_client()`, `get_model()`, `chat()` | `chat_completion()`, `generate_image()`, `download_image()`, prompt helpers | `OpenAITranslationService.translate()`, `.health_check()` | `LLMExhibitionParser.parse_exhibition_text()`, async variant |
| **Sync or async** | Async only | Sync only | Sync only | Sync only | Both (async translate, sync health) | Both |
| **SDK or raw HTTP** | `openai` (AsyncOpenAI) | `openai` (OpenAI) + `requests` | `openai` (OpenAI) | `requests` (raw) + urllib3 Retry | `openai` (OpenAI + AsyncOpenAI), `httpx` for proxy | `httpx` (raw, sync + async) |
| **Provider model** | Chain via `AI_PROVIDER_CHAIN` env | Single provider via `AppConfig` | Single provider, env fallback chain | Single provider (SenseNova only) | Single provider, constructor params | Chain via hard-coded priority (MiMo → Gemini → SiliconFlow) |
| **Environment variables** | `AI_PROVIDER_CHAIN`, `<NAME>_API_KEY`, `<NAME>_MODEL`, `<NAME>_BASE_URL` | `SENSENOVA_API_KEY` (via config) | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `OPENAI_API_KEY` | `SENSENOVA_API_KEY` | N/A (constructor params) | `XIAOMI_MIMO_API_KEY`, `GEMINI_API_KEY`, `SILICONFLOW_API_KEY` + `*_BASE_URL` |
| **Retry behavior** | Per-provider max_retries=2, exponential backoff on 429, hard fail skips to next provider | max_retries=5, exponential backoff with rate_limit_delay, temperature error recovery | None | urllib3 Retry(total=2, backoff_factor=1), session-level | Raises `LLMAPIError` on RateLimit (reads `Retry-After` header), no-proxy fallback on connection error | tenacity Retrying, stop_after_attempt(3), exp wait(1,10), retries on 429/502/503/504 |
| **Hard-fail behavior** | Pattern-matched error strings → skip to next provider & `break` | Raises after final attempt | `ValueError` on missing key | `RuntimeError` on missing key | Raises `LLMAPIError` | Returns `None` for all errors (silent, logs only) |
| **JSON handling** | `call_llm_json()`: direct parse → markdown fence extraction | None | None | None | None | Pydantic validation, markdown fence stripping, `ExhibitionModel` schema |
| **Stats** | ❌ | ✅ `call_count`, `failed_attempt_count`, `prompt_tokens`, `completion_tokens` | ❌ | ❌ | ❌ | ❌ |
| **Proxy behavior** | `PROXY`/`HTTPS_PROXY`/`HTTP_PROXY` → httpx.AsyncClient | None | None | None | Explicit no-proxy fallback on connection error (httpx with `proxy=None`, `trust_env=False`) | None |
| **Media support** | Text only | Text only | Text only | ✅ Image generation + download (SenseNova) | Text only | Text only |
| **Tests** | ✅ `tests/test_ai_provider.py` (266 lines, 12 tests, excellent) | ❌ No dedicated LLM tests | ❌ No dedicated LLM tests | ✅ `tests/test_sensenova_client.py` (156 lines, 12 tests, good) | ❌ No dedicated tests | ⚠️ `tests/test_llm_parser_cache.py` (69 lines, cache only) |

## Detailed Findings

### auto_scrape — Best provider chain implementation
The strongest candidate. Clean async design with well-defined `ProviderConfig`, module-level caching, and clear separation between chain loading, client factory, and the call loop. Its `HARD_FAIL_PATTERNS` list and rate-limit detection logic are the most robust among all candidates. The test suite is the most comprehensive (12 tests, covering all major paths).

Key pattern to adopt: `load_provider_chain()` reads `AI_PROVIDER_CHAIN` env → resolves each provider name to `<NAME>_API_KEY`/`_MODEL`/`_BASE_URL` → first is primary, rest are fallbacks.

### auto_github — Only implementation with stats tracking
The only project that tracks `call_count`, `failed_attempt_count`, `prompt_tokens`, and `completion_tokens`. Its `get_stats()` / `reset_stats()` pattern should be the model for `auto_hub.llm.stats`.

Caveat: Uses `requests` library alongside `openai` SDK (unusual). No dedicated tests.

### auto_pdf — Smallest, simplest, best first migration target
Only 74 lines. Three clean public functions (`create_client`, `get_model`, `chat`). Environment variable fallback chain is already well-structured. No retry, no JSON parsing, no stats. **Lowest risk for first migration.**

### auto_html — Only image generation implementation
The only project with media support. Uses raw `requests` (not `openai` SDK). The `generate_image()` function and `download_image()` helper are domain-specific enough to **defer from Phase 2**.

The `chat_completion()` function has reasoning-mode fallback logic that's useful for the shared layer.

### auto_lingo — Sophisticated proxy handling
The `_extract_retry_after()` static method properly reads `Retry-After` headers from `RateLimitError` responses. The no-proxy fallback pattern (double client caching) is unique and valuable.

The service class is tightly coupled to `TranslationContext` and `TranslationService` base class — extraction would be more work than other candidates. **Defer migration to Phase 4.**

### auto_curation — Most complex, highest value extraction target
404 lines with both sync and async paths. Uses `httpx` for raw HTTP (not `openai` SDK). The Pydantic validation layer (`ExhibitionModel`) is project-specific and should stay local, but the provider fallback logic and JSON fence-stripping are reusable.

Cache layer (`LLMResponseCache`) is a separate concern and should stay in `auto_curation` unless multiple projects need it.

## Abstraction Boundary Recommendation

### Extract into `auto_hub.llm`

| Component | Priority | Source inspiration |
|---|---|---|
| `ProviderConfig` model | P1 | auto_scrape |
| `ProviderChain` loader (env-driven) | P1 | auto_scrape `load_provider_chain()` |
| Sync `LLMClient` | P1 | auto_pdf `chat()` simplicity × auto_scrape patterns |
| Async `LLMClient` | P1 | auto_scrape `call_llm()` |
| Retry/backoff logic | P1 | auto_scrape (rate limit + hard fail) + auto_github (retry count + delay) |
| `call_json()` with fence stripping | P1 | auto_scrape `call_llm_json()` + auto_curation `_parse_response()` |
| Hard-fail pattern detection | P1 | auto_scrape `HARD_FAIL_PATTERNS` |
| `CallStats` with `get_stats()` / `reset_stats()` | P1 | auto_github |
| `_extract_retry_after()` for RateLimitError | P2 | auto_lingo |
| Reasoning-mode content fallback | P2 | auto_html `chat_completion()` |
| Proxy-aware client construction | P2 | auto_scrape (env proxy) + auto_lingo (no-proxy fallback) |

### Keep project-local

| Component | Reason |
|---|---|
| Domain prompts (curation, translation, ranking, summarization) | Project-specific semantics |
| `ImageGenerationClient` / `download_image()` | Specialized media handling, defer to later phase |
| `LLMResponseCache` | Only auto_curation uses it; generalize when a second project needs it |
| `health_check()` | Project-specific endpoint logic |
| `TranslationContext` / `TranslationService` base class | Translation domain |
| `ExhibitionModel` Pydantic schema | auto_curation-specific |
| Prompt engineering helpers (`enhance_prompt_for_infographic`, `summarize_markdown_for_image`) | auto_html-specific |

### Defer until proven

- Streaming response handling
- Embedding interface
- Cost accounting across projects
- Image generation abstraction
- `tenacity` integration (auto_curation uses it; standardize retry first)

## Migration Order

| Order | Project | Risk | Rationale |
|---|---|---|---|
| 1 | **auto_pdf** | Low | 74 lines, 3 public functions, no retry/JSON/stats, existing tests |
| 2 | auto_html | Low-Medium | 196 lines, shares chat but also image gen (deferred), good test coverage |
| 3 | auto_github | Medium | Shared chat + retry + stats; no tests, single-provider config |
| 4 | auto_scrape | Medium | Heavily async; test suite is the most comprehensive (266 lines) — protects migration |
| 5 | auto_curation | Medium-High | 404 lines, httpx raw, Pydantic validation, cache integration |
| 6 | auto_lingo | High | Translation-specific error handling, proxy fallback, minimal test coverage |

## Tests That Protect the First Migration (auto_pdf)

- `auto_pdf/tests/` — no dedicated LLM test file found
- Need to verify: `auto_pdf/README.md` mentions it "already has tests around LLM configuration"
- **Mitigation**: Before migrating auto_pdf, run its full test suite and confirm green.
  During migration, add tests to `auto_hub/tests/test_llm_provider_chain.py` that cover
  the fallback chain, key detection, and chat response flow.

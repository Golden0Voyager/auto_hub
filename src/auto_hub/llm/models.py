from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProviderConfig:
    name: str
    api_key: str
    base_url: str
    model: str
    is_primary: bool = False


DEFAULT_BASE_URLS: dict[str, str] = {
    "SENSENOVA": "https://api.sensenova.cn/compatible-mode/v2",
    "OPENAI": "https://api.openai.com/v1",
    "MODELSCOPE": "https://api-inference.modelscope.cn/v1",
    "GROQ": "https://api.groq.com/openai/v1",
    "OPENROUTER": "https://openrouter.ai/api/v1",
    "DEEPSEEK": "https://api.deepseek.com/v1",
}

HARD_FAIL_PATTERNS: list[str] = [
    "invalid_api_key",
    "authentication_error",
    "account_deactivated",
    "insufficient_quota",
    "model_not_found",
    "令牌已过期",
    "no endpoints found",
    "authentication",
]

RETRYABLE_STATUS_CODES: set[int] = {429, 502, 503, 504}

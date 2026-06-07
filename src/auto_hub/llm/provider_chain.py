from __future__ import annotations

import logging
import os

from auto_hub.llm.models import DEFAULT_BASE_URLS, ProviderConfig

logger = logging.getLogger("auto_hub.llm")

_primary: ProviderConfig | None = None
_fallbacks: list[ProviderConfig] = []
_chain_loaded: bool = False


def load_provider_chain() -> list[ProviderConfig]:
    """Read ``AI_PROVIDER_CHAIN`` env and build an ordered provider list.

    The first provider in the chain is treated as *primary*; the rest are
    fallbacks.  Each provider name must have a matching ``<NAME>_API_KEY``
    env var.  ``<NAME>_MODEL`` and ``<NAME>_BASE_URL`` are optional
    (defaults are looked up from ``DEFAULT_BASE_URLS``).
    """
    global _primary, _fallbacks, _chain_loaded

    if _chain_loaded:
        return [_primary, *_fallbacks] if _primary else []

    raw = os.getenv("AI_PROVIDER_CHAIN", "")
    names = [n.strip().upper() for n in raw.split(",") if n.strip()]

    providers: list[ProviderConfig] = []
    for name in names:
        api_key = os.getenv(f"{name}_API_KEY", "")
        if not api_key:
            logger.warning("Skipping provider %s: no API key", name)
            continue

        base_url = os.getenv(f"{name}_BASE_URL", DEFAULT_BASE_URLS.get(name, ""))
        model = os.getenv(f"{name}_MODEL", "")
        providers.append(
            ProviderConfig(
                name=name,
                api_key=api_key,
                base_url=base_url,
                model=model,
            )
        )

    if not providers:
        logger.error("No valid providers found in AI_PROVIDER_CHAIN")
        _chain_loaded = True
        return []

    providers[0].is_primary = True
    _primary = providers[0]
    _fallbacks = providers[1:]
    _chain_loaded = True

    logger.info(
        "Provider chain loaded: primary=%s, fallbacks=%s",
        _primary.name,
        [p.name for p in _fallbacks],
    )
    return [_primary, *_fallbacks]


def reset_provider_chain() -> None:
    """Reset cached state – for use in tests."""
    global _primary, _fallbacks, _chain_loaded
    _primary = None
    _fallbacks = []
    _chain_loaded = False

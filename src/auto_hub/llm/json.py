from __future__ import annotations

import json
import re
from typing import Any

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def parse_llm_json(raw: str) -> Any:
    """Parse an LLM response as JSON.

    Handles responses wrapped in markdown code fences.
    """
    raw_stripped = raw.strip()

    # Try direct parse first
    try:
        return json.loads(raw_stripped)
    except json.JSONDecodeError:
        pass

    # Strip markdown code blocks
    cleaned = raw_stripped
    if cleaned.startswith("```"):
        parts = cleaned.split("```", 2)
        if len(parts) >= 2:
            content = parts[1]
            if content.startswith("json"):
                content = content[4:]
            cleaned = content.strip("` \n")

    # Try again
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try regex-based extraction
    match = _JSON_BLOCK_RE.search(raw)
    if match:
        return json.loads(match.group(1))

    raise ValueError(f"LLM response is not valid JSON: {raw[:200]}")

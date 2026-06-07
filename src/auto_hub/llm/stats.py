from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CallStats:
    call_count: int = 0
    failed_attempt_count: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0

    def record(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self.call_count += 1
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens

    def record_failure(self) -> None:
        self.failed_attempt_count += 1

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    def reset(self) -> None:
        self.call_count = 0
        self.failed_attempt_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "call_count": self.call_count,
            "failed_attempt_count": self.failed_attempt_count,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
        }

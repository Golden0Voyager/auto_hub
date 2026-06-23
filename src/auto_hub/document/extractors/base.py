from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from auto_hub.document.models import ConversionResult, ConvertOptions


class BaseExtractor(ABC):
    """文本提取器抽象基类。"""

    supported_extensions: frozenset[str] = frozenset()

    @abstractmethod
    def extract(
        self,
        file_path: str | Path,
        options: ConvertOptions | None = None,
    ) -> ConversionResult:
        """将文件转换为 Markdown。"""
        raise NotImplementedError

    def can_handle(self, file_path: str | Path) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in self.supported_extensions

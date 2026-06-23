from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from auto_hub.document.models import ConvertOptions, OCRResult


class BaseOCREngine(ABC):
    """OCR 引擎抽象基类。"""

    name: str = ""

    @abstractmethod
    async def recognize(
        self,
        file_path: str | Path,
        options: ConvertOptions | None = None,
    ) -> OCRResult:
        """识别文件并返回 Markdown 文本。"""
        raise NotImplementedError

    def is_available(self) -> bool:
        """检查引擎是否可用（依赖已安装且有配置）。"""
        return True

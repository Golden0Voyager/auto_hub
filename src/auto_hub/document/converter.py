from __future__ import annotations

from pathlib import Path

from auto_hub.document.exceptions import DocumentConversionError
from auto_hub.document.models import ConversionResult, ConvertOptions


class DocumentConverter:
    """文档转 Markdown 统一入口。"""

    async def convert(
        self,
        file_path: str | Path,
        options: ConvertOptions | None = None,
    ) -> ConversionResult:
        raise DocumentConversionError("DocumentConverter 尚未实现")

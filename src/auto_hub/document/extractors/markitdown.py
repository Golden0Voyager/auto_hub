from __future__ import annotations

from pathlib import Path

from auto_hub.document.exceptions import DocumentConversionError, ExtractionError
from auto_hub.document.extractors.base import BaseExtractor
from auto_hub.document.models import ConversionResult, ConvertOptions

try:
    from markitdown import MarkItDown
except ImportError:
    MarkItDown = None  # type: ignore[assignment,misc]


class MarkItDownExtractor(BaseExtractor):
    """基于 MarkItDown 的通用文档提取器。"""

    supported_extensions: frozenset[str] = frozenset({
        ".docx", ".xls", ".xlsx", ".pptx",
        ".html", ".htm",
        ".epub",
        ".csv",
        ".txt", ".text", ".md", ".markdown", ".json", ".jsonl",
        ".msg",
        ".ipynb",
        ".wav", ".mp3", ".m4a", ".mp4",
        ".zip",
    })

    def extract(
        self,
        file_path: str | Path,
        options: ConvertOptions | None = None,
    ) -> ConversionResult:
        if MarkItDown is None:
            raise DocumentConversionError(
                "markitdown 未安装",
                suggestion="uv pip install 'auto_hub[md]'",
            )

        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        try:
            md = MarkItDown()
            result = md.convert(str(src))
            text = result.text_content or ""
        except Exception as e:
            raise ExtractionError(f"MarkItDown 提取失败: {e}") from e

        return ConversionResult(
            markdown=text,
            metadata={
                "source": "markitdown",
                "extension": src.suffix.lower(),
            },
        )

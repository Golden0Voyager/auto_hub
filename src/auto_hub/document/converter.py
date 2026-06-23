from __future__ import annotations

from pathlib import Path

from auto_hub.document.exceptions import (
    ExtractionError,
    OCREngineError,
    UnsupportedFormatError,
)
from auto_hub.document.extractors.base import BaseExtractor
from auto_hub.document.extractors.markitdown import MarkItDownExtractor
from auto_hub.document.extractors.pymupdf import PyMuPDFExtractor
from auto_hub.document.models import ConversionResult, ConvertOptions
from auto_hub.document.ocr import siliconflow  # noqa: F401 - registers OCR engines
from auto_hub.document.ocr.registry import get_ocr_engine

_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif", ".webp"})


class DocumentConverter:
    """文档转 Markdown 统一入口。"""

    def __init__(self):
        self._extractors: list[BaseExtractor] = [
            MarkItDownExtractor(),
            PyMuPDFExtractor(),
        ]

    async def convert(
        self,
        file_path: str | Path,
        options: ConvertOptions | None = None,
    ) -> ConversionResult:
        options = options or ConvertOptions()
        src = Path(file_path)

        if not src.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext = src.suffix.lower()

        # PDF / 图片：先尝试文本提取，再 fallback 到 OCR
        if ext == ".pdf" or ext in _IMAGE_EXTS:
            return await self._convert_ocr_format(src, options)

        # 其他格式：走 extractor
        for extractor in self._extractors:
            if extractor.can_handle(src):
                return extractor.extract(src, options)

        raise UnsupportedFormatError(ext)

    async def _convert_ocr_format(
        self,
        src: Path,
        options: ConvertOptions,
    ) -> ConversionResult:
        ext = src.suffix.lower()

        # 图片：直接 OCR
        if ext in _IMAGE_EXTS:
            return await self._run_ocr(src, options)

        # PDF：先尝试 PyMuPDF 文本提取
        if not options.force_ocr:
            try:
                extractor = PyMuPDFExtractor()
                result = extractor.extract(src, options)
                if result.markdown.strip():
                    return result
            except ExtractionError:
                pass

        return await self._run_ocr(src, options)

    async def _run_ocr(self, src: Path, options: ConvertOptions) -> ConversionResult:
        engine_name = options.ocr_engine or "siliconflow"
        try:
            engine = get_ocr_engine(engine_name)
        except OCREngineError:
            raise

        ocr_result = await engine.recognize(src, options)
        return ConversionResult(
            markdown=ocr_result.text,
            metadata={
                "source": "ocr",
                "engine": ocr_result.engine,
                "pages": ocr_result.pages,
                "extension": src.suffix.lower(),
            },
        )

from __future__ import annotations

import re
from pathlib import Path

from auto_hub.document.exceptions import DocumentConversionError, ExtractionError
from auto_hub.document.extractors.base import BaseExtractor
from auto_hub.document.models import ConversionResult, ConvertOptions

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore[assignment]


class PyMuPDFExtractor(BaseExtractor):
    """基于 PyMuPDF 的文本型 PDF 提取器，智能去除页眉页脚。"""

    supported_extensions: frozenset[str] = frozenset({".pdf"})

    def __init__(self, header_footer_threshold: float = 0.7):
        self.header_footer_threshold = header_footer_threshold

    def extract(
        self,
        file_path: str | Path,
        options: ConvertOptions | None = None,
    ) -> ConversionResult:
        if fitz is None:
            raise DocumentConversionError(
                "PyMuPDF 未安装",
                suggestion="uv pip install 'auto_hub[md]'",
            )

        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        try:
            text = self._extract_text(str(src))
        except Exception as e:
            raise ExtractionError(f"PyMuPDF 提取失败: {e}") from e

        return ConversionResult(
            markdown=text,
            metadata={
                "source": "pymupdf",
                "extension": ".pdf",
                "pages": self._count_pages(str(src)),
            },
        )

    def _count_pages(self, pdf_path: str) -> int:
        doc = fitz.open(pdf_path)
        try:
            return len(doc)
        finally:
            doc.close()

    def _extract_text(self, pdf_path: str) -> str:
        doc = fitz.open(pdf_path)
        try:
            pages_data = []
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text()
                if text and text.strip():
                    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                    pages_data.append({
                        "page_num": page_num + 1,
                        "lines": lines,
                        "text": text.strip(),
                    })

            if not pages_data:
                return ""

            header_footer = self._detect_header_footer(pages_data)
            return self._build_clean_text(pages_data, header_footer)
        finally:
            doc.close()

    def _detect_header_footer(self, pages_data: list[dict]) -> set[str]:
        line_counts: dict[str, int] = {}
        for page in pages_data:
            for line in page["lines"]:
                line_counts[line] = line_counts.get(line, 0) + 1

        threshold = max(2, len(pages_data) * self.header_footer_threshold)

        return {
            line
            for line, count in line_counts.items()
            if count >= threshold or re.match(r"^\d+$", line)
        }

    def _build_clean_text(self, pages_data: list[dict], header_footer: set[str]) -> str:
        parts = []
        for page in pages_data:
            filtered = [ln for ln in page["lines"] if ln not in header_footer]
            if not filtered:
                continue
            parts.append(f"[PAGE:{page['page_num']}]")
            parts.append("\n".join(filtered))
        return "\n\n".join(parts)

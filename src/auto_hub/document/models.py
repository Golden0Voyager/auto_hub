from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DocumentType(StrEnum):
    PDF = "pdf"
    IMAGE = "image"
    OFFICE = "office"
    MARKUP = "markup"
    DATA = "data"
    AUDIO = "audio"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"


class ConvertOptions(BaseModel):
    ocr_engine: str | None = Field(default=None, description="OCR 引擎名称")
    force_ocr: bool = Field(default=False, description="强制 OCR")
    language: str = Field(default="zh", description="OCR 语言")
    image_dpi: int = Field(default=200, description="PDF 渲染 DPI")
    preserve_layout: bool = Field(default=False, description="保留版面信息")
    output_path: str | None = Field(default=None, description="输出文件路径")


class OCRResult(BaseModel):
    text: str
    engine: str
    pages: int = 0
    language: str = "zh"


class ConversionResult(BaseModel):
    markdown: str
    metadata: dict[str, Any] = Field(default_factory=dict)

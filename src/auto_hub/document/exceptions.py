from __future__ import annotations


class DocumentConversionError(Exception):
    """文档转换异常基类。"""

    def __init__(self, message: str, suggestion: str | None = None):
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion

    def __str__(self) -> str:
        if self.suggestion:
            return f"{self.message}\n建议: {self.suggestion}"
        return self.message


class UnsupportedFormatError(DocumentConversionError):
    """不支持的文件格式。"""

    def __init__(self, ext: str):
        super().__init__(f"不支持的文件格式: {ext}")


class ExtractionError(DocumentConversionError):
    """文本提取失败。"""
    pass


class OCREngineError(DocumentConversionError):
    """OCR 引擎错误。"""
    pass

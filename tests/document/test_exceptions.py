from __future__ import annotations

from auto_hub.document.exceptions import (
    DocumentConversionError,
    ExtractionError,
    OCREngineError,
    UnsupportedFormatError,
)


def test_document_conversion_error_with_suggestion():
    err = DocumentConversionError("出错了", suggestion="请重试")
    assert str(err) == "出错了\n建议: 请重试"


def test_document_conversion_error_without_suggestion():
    err = DocumentConversionError("简单错误")
    assert str(err) == "简单错误"
    assert err.suggestion is None


def test_unsupported_format_error():
    err = UnsupportedFormatError(".xyz")
    assert str(err) == "不支持的文件格式: .xyz"
    assert isinstance(err, DocumentConversionError)


def test_extraction_error_is_subclass():
    err = ExtractionError("提取失败")
    assert isinstance(err, DocumentConversionError)
    assert "提取失败" in str(err)


def test_ocr_engine_error_is_subclass():
    err = OCREngineError("引擎错误")
    assert isinstance(err, DocumentConversionError)
    assert "引擎错误" in str(err)


def test_ocr_engine_error_with_suggestion():
    err = OCREngineError("未知引擎", suggestion="请检查拼写")
    assert "建议" in str(err)

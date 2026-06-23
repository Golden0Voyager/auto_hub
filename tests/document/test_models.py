from __future__ import annotations

from auto_hub.document.models import ConversionResult, ConvertOptions


def test_convert_options_defaults():
    opts = ConvertOptions()
    assert opts.ocr_engine is None
    assert opts.force_ocr is False
    assert opts.language == "zh"
    assert opts.image_dpi == 200


def test_conversion_result_model():
    result = ConversionResult(markdown="# Hello", metadata={"pages": 1})
    assert result.markdown == "# Hello"
    assert result.metadata["pages"] == 1

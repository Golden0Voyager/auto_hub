from __future__ import annotations

import pytest

from auto_hub.document.exceptions import OCREngineError
from auto_hub.document.ocr.registry import get_ocr_engine
from auto_hub.document.ocr.siliconflow import SiliconFlowOCREngine


def test_registry_returns_siliconflow_engine():
    engine = get_ocr_engine("siliconflow")
    assert isinstance(engine, SiliconFlowOCREngine)


def test_registry_unknown_engine_raises():
    with pytest.raises(OCREngineError) as exc_info:
        get_ocr_engine("unknown")
    assert "未知 OCR 引擎" in str(exc_info.value)


def test_siliconflow_engine_missing_openai(monkeypatch):
    monkeypatch.setattr(
        "auto_hub.document.ocr.siliconflow.OpenAI",
        None,
    )
    with pytest.raises(OCREngineError) as exc_info:
        SiliconFlowOCREngine()
    assert "openai 包未安装" in str(exc_info.value)

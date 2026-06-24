from __future__ import annotations

import asyncio
import builtins
import importlib
import sys
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from auto_hub.document.exceptions import OCREngineError
from auto_hub.document.models import ConvertOptions
from auto_hub.document.ocr.base import BaseOCREngine
from auto_hub.document.ocr.registry import _REGISTRY, get_ocr_engine, register_engine
from auto_hub.document.ocr.siliconflow import SiliconFlowOCREngine


def test_registry_returns_siliconflow_engine():
    engine = get_ocr_engine("siliconflow")
    assert isinstance(engine, SiliconFlowOCREngine)


def test_registry_unknown_engine_raises():
    with pytest.raises(OCREngineError) as exc_info:
        get_ocr_engine("unknown")
    assert "未知 OCR 引擎" in str(exc_info.value)


def test_registry_list_engines():
    engines = _REGISTRY.list_engines()
    assert "siliconflow" in engines
    assert isinstance(engines, list)


def test_registry_register_dynamically():
    class DummyEngine(BaseOCREngine):
        name = "dummy"

        async def recognize(self, file_path, options=None):
            return None

    register_engine(DummyEngine)
    engine = get_ocr_engine("dummy")
    assert isinstance(engine, DummyEngine)
    engines = _REGISTRY.list_engines()
    assert "dummy" in engines


def test_siliconflow_engine_missing_openai(monkeypatch):
    monkeypatch.setattr(
        "auto_hub.document.ocr.siliconflow.OpenAI",
        None,
    )
    with pytest.raises(OCREngineError) as exc_info:
        SiliconFlowOCREngine()
    assert "openai 包未安装" in str(exc_info.value)


def test_base_ocr_engine_raises_not_implemented():
    class BadEngine(BaseOCREngine):
        async def recognize(self, file_path, options=None):
            return await super().recognize(file_path, options)

    engine = BadEngine()
    with pytest.raises(NotImplementedError):
        asyncio.run(engine.recognize("dummy.txt"))


def test_base_ocr_engine_is_available():
    class ConcreteEngine(BaseOCREngine):
        name = "test"

        async def recognize(self, file_path, options=None):
            return None

    engine = ConcreteEngine()
    assert engine.is_available() is True


def test_detect_mime_type_jpeg():
    engine = SiliconFlowOCREngine(api_key="test-key")
    assert engine._detect_mime_type(b"\xff\xd8\xff\xe0") == "image/jpeg"


def test_detect_mime_type_png():
    engine = SiliconFlowOCREngine(api_key="test-key")
    assert engine._detect_mime_type(b"\x89PNG\r\n\x1a\n") == "image/png"


def test_detect_mime_type_webp():
    engine = SiliconFlowOCREngine(api_key="test-key")
    assert engine._detect_mime_type(b"RIFF\x00\x00\x00\x00WEBP") == "image/webp"


def test_detect_mime_type_gif():
    engine = SiliconFlowOCREngine(api_key="test-key")
    assert engine._detect_mime_type(b"GIF89a") == "image/gif"


def test_detect_mime_type_bmp():
    engine = SiliconFlowOCREngine(api_key="test-key")
    assert engine._detect_mime_type(b"BM\x00\x00") == "image/bmp"


def test_detect_mime_type_tiff_le():
    engine = SiliconFlowOCREngine(api_key="test-key")
    assert engine._detect_mime_type(b"II\x2a\x00") == "image/tiff"


def test_detect_mime_type_tiff_be():
    engine = SiliconFlowOCREngine(api_key="test-key")
    assert engine._detect_mime_type(b"MM\x00\x2a") == "image/tiff"


def test_detect_mime_type_fallback():
    engine = SiliconFlowOCREngine(api_key="test-key")
    assert engine._detect_mime_type(b"\x00\x00\x00\x00") == "image/png"


def test_get_api_key_from_init():
    engine = SiliconFlowOCREngine(api_key="init-key")
    assert engine._get_api_key() == "init-key"


def test_get_api_key_from_env_siliconflow(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "env-sf-key")
    engine = SiliconFlowOCREngine()
    assert engine._get_api_key() == "env-sf-key"


def test_get_api_key_from_env_sensenova(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    monkeypatch.setenv("SENSENOVA_API_KEY", "env-sn-key")
    engine = SiliconFlowOCREngine()
    assert engine._get_api_key() == "env-sn-key"


def test_get_api_key_missing(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    monkeypatch.delenv("SENSENOVA_API_KEY", raising=False)
    engine = SiliconFlowOCREngine()
    with pytest.raises(OCREngineError) as exc_info:
        engine._get_api_key()
    assert "未配置 SiliconFlow API Key" in str(exc_info.value)


def test_client_lazy_init(mocker: MockerFixture):
    engine = SiliconFlowOCREngine(api_key="test-key")
    mock_openai = mocker.patch("auto_hub.document.ocr.siliconflow.OpenAI")
    client = engine.client
    assert client is engine._client
    mock_openai.assert_called_once_with(
        api_key="test-key",
        base_url="https://api.siliconflow.cn/v1",
    )


def test_client_cached(mocker: MockerFixture):
    engine = SiliconFlowOCREngine(api_key="test-key")
    mock_client = mocker.MagicMock()
    engine._client = mock_client
    mock_openai = mocker.patch("auto_hub.document.ocr.siliconflow.OpenAI")
    client = engine.client
    assert client is mock_client
    mock_openai.assert_not_called()


def test_ocr_image_success(mocker: MockerFixture):
    engine = SiliconFlowOCREngine(api_key="test-key")
    mock_client = mocker.MagicMock()
    mock_client.chat.completions.create.return_value = mocker.MagicMock(
        choices=[mocker.MagicMock(message=mocker.MagicMock(content="OCR output"))]
    )
    engine._client = mock_client
    result = engine._ocr_image(b"fake-image", "Free OCR.")
    assert result == "OCR output"


def test_ocr_image_empty_content(mocker: MockerFixture):
    engine = SiliconFlowOCREngine(api_key="test-key")
    mock_client = mocker.MagicMock()
    mock_client.chat.completions.create.return_value = mocker.MagicMock(
        choices=[mocker.MagicMock(message=mocker.MagicMock(content=None))]
    )
    engine._client = mock_client
    result = engine._ocr_image(b"fake-image", "Free OCR.")
    assert result == ""


@pytest.mark.asyncio
async def test_recognize_image_file(mocker: MockerFixture, tmp_path: Path):
    engine = SiliconFlowOCREngine(api_key="test-key")
    mocker.patch.object(engine, "_ocr_image", return_value="Image text")

    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")

    result = await engine.recognize(img)
    assert result.text == "Image text"
    assert result.engine == "siliconflow"
    assert result.pages == 1
    assert result.language == "zh"


@pytest.mark.asyncio
async def test_recognize_image_with_options(mocker: MockerFixture, tmp_path: Path):
    engine = SiliconFlowOCREngine(api_key="test-key")
    mocker.patch.object(engine, "_ocr_image", return_value="Image text")
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0")

    result = await engine.recognize(img, ConvertOptions(language="en"))
    assert result.text == "Image text"
    assert result.pages == 1
    assert result.language == "en"


@pytest.mark.asyncio
async def test_recognize_pdf_single_page(mocker: MockerFixture, fixtures_dir: Path):
    engine = SiliconFlowOCREngine(api_key="test-key")
    mocker.patch.object(engine, "_ocr_image", return_value="PDF page OCR")

    result = await engine.recognize(fixtures_dir / "sample.pdf")
    assert "PDF page OCR" in result.text
    assert result.engine == "siliconflow"
    assert result.pages == 1


@pytest.mark.asyncio
async def test_recognize_pdf_multi_page(mocker: MockerFixture, tmp_path: Path):
    import fitz

    doc = fitz.open()
    for _ in range(3):
        page = doc.new_page()
        page.insert_text((50, 50), "Page content")
    pdf_path = tmp_path / "multi.pdf"
    doc.save(str(pdf_path))
    doc.close()

    engine = SiliconFlowOCREngine(api_key="test-key")
    mocker.patch.object(engine, "_ocr_image", return_value="Page OCR")

    result = await engine.recognize(pdf_path)
    assert "第 1 页" in result.text
    assert "第 2 页" in result.text
    assert "第 3 页" in result.text
    assert result.pages == 3


@pytest.mark.asyncio
async def test_recognize_file_not_found():
    engine = SiliconFlowOCREngine(api_key="test-key")
    with pytest.raises(FileNotFoundError):
        await engine.recognize("nonexistent.pdf")


@pytest.mark.asyncio
async def test_recognize_missing_fitz(monkeypatch):
    monkeypatch.setattr("auto_hub.document.ocr.siliconflow.fitz", None)
    engine = SiliconFlowOCREngine(api_key="test-key")
    with pytest.raises(OCREngineError) as exc_info:
        await engine.recognize("dummy.pdf")
    assert "PyMuPDF 未安装" in str(exc_info.value)


@pytest.mark.asyncio
async def test_recognize_without_options(mocker: MockerFixture, tmp_path: Path):
    engine = SiliconFlowOCREngine(api_key="test-key")
    mocker.patch.object(engine, "_ocr_image", return_value="text")
    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    result = await engine.recognize(img)
    assert result.text == "text"


def _reimport_module(module_path: str, blocked: set[str], monkeypatch):
    """Re-import a module with certain dependencies blocked (covers except ImportError)."""
    orig_modules = {}
    for name in list(sys.modules.keys()):
        if name == module_path or name in blocked:
            orig_modules[name] = sys.modules.pop(name, None)

    orig_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name in blocked:
            raise ImportError(f"No module named {name}")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    mod = importlib.import_module(module_path)

    if module_path in sys.modules:
        del sys.modules[module_path]
    for name, orig_mod in orig_modules.items():
        if orig_mod is not None:
            sys.modules[name] = orig_mod

    return mod


def test_siliconflow_import_fallbacks(monkeypatch):
    """Cover except ImportError branches for fitz and openai in siliconflow.py."""
    mod = _reimport_module(
        "auto_hub.document.ocr.siliconflow",
        {"fitz", "openai"},
        monkeypatch,
    )
    assert mod.fitz is None
    assert mod.OpenAI is None

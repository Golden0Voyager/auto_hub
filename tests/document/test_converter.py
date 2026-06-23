from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from auto_hub.document.converter import _IMAGE_EXTS, DocumentConverter
from auto_hub.document.exceptions import ExtractionError, UnsupportedFormatError
from auto_hub.document.models import ConversionResult, ConvertOptions, OCRResult


@pytest.fixture
def converter() -> DocumentConverter:
    return DocumentConverter()


@pytest.mark.asyncio
async def test_convert_markdown_file(converter: DocumentConverter, fixtures_dir: Path, mocker: MockerFixture):
    mocker.patch(
        "auto_hub.document.converter.MarkItDownExtractor.extract",
        return_value=ConversionResult(
            markdown="# Sample Document\n\nThis is a sample markdown file for testing.",
            metadata={"source": "markitdown", "extension": ".md"},
        ),
    )
    result = await converter.convert(fixtures_dir / "sample.md")
    assert "Sample Document" in result.markdown
    assert result.metadata["source"] == "markitdown"


@pytest.mark.asyncio
async def test_convert_text_pdf(converter: DocumentConverter, fixtures_dir: Path):
    result = await converter.convert(fixtures_dir / "sample.pdf")
    assert "Hello World" in result.markdown
    assert result.metadata["source"] == "pymupdf"


@pytest.mark.asyncio
async def test_convert_unsupported_format(converter: DocumentConverter, tmp_path: Path):
    unsupported = tmp_path / "unknown.xyz"
    unsupported.write_text("dummy")
    with pytest.raises(UnsupportedFormatError):
        await converter.convert(unsupported)


@pytest.mark.asyncio
async def test_convert_file_not_found(converter: DocumentConverter):
    with pytest.raises(FileNotFoundError):
        await converter.convert("nonexistent.pdf")


@pytest.mark.asyncio
async def test_convert_pdf_force_ocr(converter: DocumentConverter, fixtures_dir: Path, mocker: MockerFixture):
    """PDF with force_ocr=True should skip text extraction and go to OCR."""
    mock_engine = mocker.AsyncMock()
    mock_engine.recognize = mocker.AsyncMock(return_value=OCRResult(
        text="# OCR Result\n\nHello",
        engine="siliconflow",
        pages=1,
        language="zh",
    ))
    mocker.patch("auto_hub.document.converter.get_ocr_engine", return_value=mock_engine)

    options = ConvertOptions(force_ocr=True)
    result = await converter.convert(fixtures_dir / "sample.pdf", options)

    assert "OCR Result" in result.markdown
    assert result.metadata["source"] == "ocr"
    assert result.metadata["engine"] == "siliconflow"
    mock_engine.recognize.assert_awaited_once()


@pytest.mark.asyncio
async def test_convert_pdf_extraction_error_fallback_to_ocr(converter: DocumentConverter, fixtures_dir: Path, mocker: MockerFixture):
    """PDF with ExtractionError should fallback to OCR."""
    mock_engine = mocker.AsyncMock()
    mock_engine.recognize = mocker.AsyncMock(return_value=OCRResult(
        text="# OCR Extraction Error Fallback\n\nExtracted via OCR",
        engine="siliconflow",
        pages=1,
        language="zh",
    ))
    mocker.patch("auto_hub.document.converter.get_ocr_engine", return_value=mock_engine)

    # Patch PyMuPDFExtractor to raise ExtractionError
    mocker.patch(
        "auto_hub.document.converter.PyMuPDFExtractor.extract",
        side_effect=ExtractionError("PyMuPDF failed"),
    )

    result = await converter.convert(fixtures_dir / "sample.pdf")

    assert "OCR Extraction Error Fallback" in result.markdown
    assert result.metadata["source"] == "ocr"
    mock_engine.recognize.assert_awaited_once()


@pytest.mark.asyncio
async def test_convert_image_direct_ocr(converter: DocumentConverter, tmp_path: Path, mocker: MockerFixture):
    """Image files should go directly to OCR."""
    # Create a dummy image file
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    mock_engine = mocker.AsyncMock()
    mock_engine.recognize = mocker.AsyncMock(return_value=OCRResult(
        text="# Image OCR\n\nHello from image",
        engine="siliconflow",
        pages=1,
        language="zh",
    ))
    mocker.patch("auto_hub.document.converter.get_ocr_engine", return_value=mock_engine)

    result = await converter.convert(img_path)

    assert "Image OCR" in result.markdown
    assert result.metadata["source"] == "ocr"
    assert result.metadata["extension"] == ".png"
    mock_engine.recognize.assert_awaited_once()


@pytest.mark.asyncio
async def test_convert_ocr_engine_error(converter: DocumentConverter, tmp_path: Path, mocker: MockerFixture):
    """OCR engine error should propagate."""
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    mocker.patch(
        "auto_hub.document.converter.get_ocr_engine",
        side_effect=Exception("OCR engine not found"),
    )

    with pytest.raises(Exception, match="OCR engine not found"):
        await converter.convert(img_path)


@pytest.mark.asyncio
async def test_convert_with_options(converter: DocumentConverter, fixtures_dir: Path, mocker: MockerFixture):
    """Convert with default options should work."""
    mocker.patch(
        "auto_hub.document.converter.MarkItDownExtractor.extract",
        return_value=ConversionResult(
            markdown="# Sample Document\n\nThis is a sample markdown file for testing.",
            metadata={"source": "markitdown", "extension": ".md"},
        ),
    )
    result = await converter.convert(fixtures_dir / "sample.md", ConvertOptions())
    assert "Sample Document" in result.markdown


def test_image_exts_constant():
    """_IMAGE_EXTS should contain expected extensions."""
    assert ".png" in _IMAGE_EXTS
    assert ".jpg" in _IMAGE_EXTS
    assert ".jpeg" in _IMAGE_EXTS
    assert ".pdf" not in _IMAGE_EXTS

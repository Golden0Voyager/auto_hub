from __future__ import annotations

import builtins
import importlib
import sys
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from auto_hub.document.exceptions import ExtractionError
from auto_hub.document.extractors.base import BaseExtractor
from auto_hub.document.extractors.markitdown import MarkItDownExtractor
from auto_hub.document.extractors.pymupdf import PyMuPDFExtractor


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


def test_base_extractor_raises_not_implemented():
    class BadExtractor(BaseExtractor):
        def extract(self, file_path, options=None):
            return super().extract(file_path, options)

    extractor = BadExtractor()
    with pytest.raises(NotImplementedError):
        extractor.extract("dummy.txt")


def test_markitdown_extractor_can_handle_markdown(fixtures_dir: Path):
    extractor = MarkItDownExtractor()
    assert extractor.can_handle(fixtures_dir / "sample.md")


def test_markitdown_extractor_extracts_markdown(fixtures_dir: Path):
    extractor = MarkItDownExtractor()
    result = extractor.extract(fixtures_dir / "sample.md")
    assert "Sample Document" in result.markdown
    assert result.metadata["source"] == "markitdown"


def test_markitdown_extractor_missing_dependency(monkeypatch):
    monkeypatch.setattr(
        "auto_hub.document.extractors.markitdown.MarkItDown",
        None,
    )
    extractor = MarkItDownExtractor()
    with pytest.raises(Exception) as exc_info:
        extractor.extract("dummy.md")
    assert "markitdown 未安装" in str(exc_info.value)


def test_markitdown_extractor_file_not_found():
    extractor = MarkItDownExtractor()
    with pytest.raises(FileNotFoundError):
        extractor.extract("nonexistent.docx")


def test_markitdown_extractor_extraction_error(mocker: MockerFixture, fixtures_dir: Path):
    mock_markitdown = mocker.patch(
        "auto_hub.document.extractors.markitdown.MarkItDown"
    )
    mock_markitdown.return_value.convert.side_effect = ValueError("bad file format")

    extractor = MarkItDownExtractor()
    with pytest.raises(ExtractionError) as exc_info:
        extractor.extract(fixtures_dir / "sample.md")
    assert "MarkItDown 提取失败" in str(exc_info.value)


def test_pymupdf_extractor_extracts_text(fixtures_dir: Path):
    extractor = PyMuPDFExtractor()
    result = extractor.extract(fixtures_dir / "sample.pdf")
    assert "Hello World" in result.markdown
    assert result.metadata["source"] == "pymupdf"


def test_pymupdf_extractor_missing_dependency(monkeypatch):
    monkeypatch.setattr(
        "auto_hub.document.extractors.pymupdf.fitz",
        None,
    )
    extractor = PyMuPDFExtractor()
    with pytest.raises(Exception) as exc_info:
        extractor.extract("dummy.pdf")
    assert "PyMuPDF 未安装" in str(exc_info.value)


def test_pymupdf_extractor_file_not_found():
    extractor = PyMuPDFExtractor()
    with pytest.raises(FileNotFoundError):
        extractor.extract("nonexistent.pdf")


def test_pymupdf_extractor_extraction_error(mocker: MockerFixture, fixtures_dir: Path):
    extractor = PyMuPDFExtractor()
    mocker.patch.object(
        extractor,
        "_extract_text",
        side_effect=ValueError("corrupt PDF"),
    )
    with pytest.raises(ExtractionError) as exc_info:
        extractor.extract(fixtures_dir / "sample.pdf")
    assert "PyMuPDF 提取失败" in str(exc_info.value)


@pytest.fixture
def empty_pdf(tmp_path: Path) -> Path:
    import fitz

    doc = fitz.open()
    doc.new_page()
    path = tmp_path / "empty.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_pymupdf_extractor_empty_pdf(empty_pdf: Path):
    """PDF with no extractable text should return empty string."""
    extractor = PyMuPDFExtractor()
    result = extractor.extract(empty_pdf)
    assert result.markdown == ""


@pytest.fixture
def repeated_content_pdf(tmp_path: Path) -> Path:
    """2-page PDF where all content repeats across pages, triggering header/footer filter."""
    import fitz

    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page()
        page.insert_text((50, 50), "PageHeader")
        page.insert_text((50, 100), "PageBody")
        page.insert_text((50, 750), "99")
    path = tmp_path / "repeated.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_pymupdf_extractor_all_lines_filtered(repeated_content_pdf: Path):
    """When every line is detected as header/footer, output should be empty."""
    extractor = PyMuPDFExtractor()
    result = extractor.extract(repeated_content_pdf)
    assert result.markdown == ""


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

    # Restore originals (monkeypatch auto-restores __import__)
    if module_path in sys.modules:
        del sys.modules[module_path]
    for name, orig_mod in orig_modules.items():
        if orig_mod is not None:
            sys.modules[name] = orig_mod

    return mod


def test_markitdown_import_fallback(monkeypatch):
    """Cover the except ImportError branch in markitdown.py."""
    mod = _reimport_module(
        "auto_hub.document.extractors.markitdown",
        {"markitdown"},
        monkeypatch,
    )
    assert mod.MarkItDown is None


def test_pymupdf_import_fallback(monkeypatch):
    """Cover the except ImportError branch in pymupdf.py."""
    mod = _reimport_module(
        "auto_hub.document.extractors.pymupdf",
        {"fitz"},
        monkeypatch,
    )
    assert mod.fitz is None

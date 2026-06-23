from __future__ import annotations

from pathlib import Path

import pytest

from auto_hub.document.extractors.markitdown import MarkItDownExtractor


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


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

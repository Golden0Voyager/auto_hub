from __future__ import annotations

from auto_hub.document.exceptions import OCREngineError
from auto_hub.document.ocr.base import BaseOCREngine


class OCRRegistry:
    """OCR 引擎注册表。"""

    def __init__(self) -> None:
        self._engines: dict[str, type[BaseOCREngine]] = {}

    def register(self, engine_class: type[BaseOCREngine]) -> None:
        self._engines[engine_class.name] = engine_class

    def get(self, name: str) -> BaseOCREngine:
        if name not in self._engines:
            available = ", ".join(self._engines.keys()) or "无"
            raise OCREngineError(
                f"未知 OCR 引擎: {name}",
                suggestion=f"可用引擎: {available}",
            )
        return self._engines[name]()

    def list_engines(self) -> list[str]:
        return list(self._engines.keys())


_REGISTRY = OCRRegistry()


def register_engine(engine_class: type[BaseOCREngine]) -> type[BaseOCREngine]:
    _REGISTRY.register(engine_class)
    return engine_class


def get_ocr_engine(name: str) -> BaseOCREngine:
    return _REGISTRY.get(name)

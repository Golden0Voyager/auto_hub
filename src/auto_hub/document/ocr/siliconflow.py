from __future__ import annotations

import base64
import os
from pathlib import Path

from auto_hub.document.exceptions import OCREngineError
from auto_hub.document.models import ConvertOptions, OCRResult
from auto_hub.document.ocr.base import BaseOCREngine
from auto_hub.document.ocr.registry import register_engine

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore[assignment]

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]


_BASE_URL = "https://api.siliconflow.cn/v1"
_MODEL = "deepseek-ai/DeepSeek-OCR"
_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif", ".webp"})
_PROMPT_FREE = "<image>\nFree OCR."


@register_engine
class SiliconFlowOCREngine(BaseOCREngine):
    """SiliconFlow DeepSeek-OCR 引擎。"""

    name = "siliconflow"

    def __init__(self, api_key: str | None = None):
        if OpenAI is None:
            raise OCREngineError(
                "openai 包未安装",
                suggestion="uv pip install 'auto_hub[ocr]'",
            )
        self._api_key = api_key
        self._client: OpenAI | None = None

    def _get_api_key(self) -> str:
        if self._api_key:
            return self._api_key
        key = os.getenv("SILICONFLOW_API_KEY") or os.getenv("SENSENOVA_API_KEY")
        if not key:
            raise OCREngineError(
                "未配置 SiliconFlow API Key",
                suggestion="设置 SILICONFLOW_API_KEY 或 SENSENOVA_API_KEY 环境变量",
            )
        return key

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self._get_api_key(), base_url=_BASE_URL)
        return self._client

    def _detect_mime_type(self, image_bytes: bytes) -> str:
        """从文件魔数检测 MIME 类型。"""
        if image_bytes[:2] == b"\xff\xd8":
            return "image/jpeg"
        elif image_bytes[:4] == b"\x89PNG":
            return "image/png"
        elif image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
            return "image/webp"
        elif image_bytes[:3] == b"GIF":
            return "image/gif"
        elif image_bytes[:2] == b"BM":
            return "image/bmp"
        return "image/png"

    def _ocr_image(self, image_bytes: bytes, prompt: str, max_tokens: int = 8000) -> str:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        mime_type = self._detect_mime_type(image_bytes)
        resp = self.client.chat.completions.create(
            model=_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
            max_tokens=max_tokens,
            temperature=0.1,
        )
        content = resp.choices[0].message.content
        return content.strip() if content else ""

    async def recognize(
        self,
        file_path: str | Path,
        options: ConvertOptions | None = None,
    ) -> OCRResult:
        if fitz is None:
            raise OCREngineError(
                "PyMuPDF 未安装",
                suggestion="uv pip install 'auto_hub[md]'",
            )

        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        options = options or ConvertOptions()
        prompt = _PROMPT_FREE
        dpi = options.image_dpi

        ext = src.suffix.lower()
        if ext in _IMAGE_EXTS:
            text = self._ocr_image(src.read_bytes(), prompt)
            pages = 1
        else:
            doc = fitz.open(str(src))
            try:
                pages = len(doc)
                parts = []
                for page_num in range(pages):
                    page = doc[page_num]
                    pix = page.get_pixmap(dpi=dpi)
                    img_bytes = pix.tobytes("png")
                    result = self._ocr_image(img_bytes, prompt)
                    parts.append(f"## 第 {page_num + 1} 页\n\n{result}")
                text = "\n\n".join(parts)
            finally:
                doc.close()

        return OCRResult(
            text=text,
            engine=self.name,
            pages=pages,
            language=options.language,
        )

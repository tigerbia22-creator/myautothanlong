"""Real CPU neural OCR, lazily loaded from RapidOCR's bundled ONNX models."""
from __future__ import annotations

import importlib.util
import math
import threading
import time

from PIL import Image

MODEL_NAME = "RapidOCR 3.10 · mô hình ONNX đi kèm · CPU"


class OCRReader:
    def __init__(self):
        self._engine = None
        self._lock = threading.RLock()
        self.error = None

    def info(self):
        return {"available": importlib.util.find_spec("rapidocr") is not None and importlib.util.find_spec("onnxruntime") is not None,
                "ready": self._engine is not None, "model": MODEL_NAME, "error": self.error}

    def _load(self):
        if self._engine is not None:
            return
        try:
            from rapidocr import RapidOCR
            self._engine = RapidOCR(params={
                "Global.use_cls": False, "Global.text_score": 0.35,
                "Global.log_level": "warning", "Det.limit_type": "max", "Det.limit_side_len": 1536,
                "EngineConfig.onnxruntime.intra_op_num_threads": 2,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            })
            self.error = None
        except ImportError as exc:
            self.error = f"Không nạp được OCR AI: {exc}. Đóng bản đang chạy và mở CHAY_TREN_WINDOWS_AI.bat."
            raise RuntimeError(self.error) from exc
        except Exception as exc:
            self.error = f"Không khởi tạo được mô hình OCR: {exc}"
            raise RuntimeError(self.error) from exc

    def read(self, image, region=None):
        if not isinstance(image, Image.Image):
            raise ValueError("OCR cần ảnh màn hình hợp lệ.")
        x, y, width, height = (0, 0, image.width, image.height) if region is None else region
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (x, y, width, height)):
            raise ValueError("Vùng OCR cần tọa độ nguyên.")
        if x < 0 or y < 0 or width < 1 or height < 1 or x + width > image.width or y + height > image.height:
            raise ValueError("Vùng OCR nằm ngoài màn hình.")
        crop = image.crop((x, y, x + width, y + height)).convert("RGB")
        scale = min(3.0, max(1.0, 1400 / max(width, height)))
        resized = crop.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)
        sx, sy = resized.width / width, resized.height / height
        with self._lock:
            self._load()
            result = self._engine(resized)
        items = []
        if result.txts:
            for text, score, points in zip(result.txts, result.scores, result.boxes):
                confidence = float(score)
                if not math.isfinite(confidence):
                    continue
                left = max(x, math.floor(min(float(p[0]) for p in points) / sx + x))
                top = max(y, math.floor(min(float(p[1]) for p in points) / sy + y))
                right = min(x + width, math.ceil(max(float(p[0]) for p in points) / sx + x))
                bottom = min(y + height, math.ceil(max(float(p[1]) for p in points) / sy + y))
                if right > left and bottom > top:
                    items.append({"text": str(text), "confidence": confidence,
                                  "box": [left, top, right - left, bottom - top]})
        return items

    def probe(self, image):
        start = time.monotonic()
        items = self.read(image)
        return {"items": items, "elapsed_ms": round((time.monotonic() - start) * 1000), "model": MODEL_NAME}

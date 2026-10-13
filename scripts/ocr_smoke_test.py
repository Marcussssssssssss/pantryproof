"""Run a minimal PaddleOCR 3.7 inference test on a synthetic receipt."""

from __future__ import annotations

import json
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

import paddle
from paddleocr import PaddleOCR
from PIL import Image, ImageDraw, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "data" / "working" / "ocr_smoke"
IMAGE_PATH = OUTPUT_DIR / "synthetic_receipt.png"
RAW_OUTPUT_PATH = OUTPUT_DIR / "raw_ocr_output.json"
VISUALIZATION_PATH = OUTPUT_DIR / "ocr_visualization.png"
CONFIG_PATH = OUTPUT_DIR / "paddlex_ocr_config.yaml"
METADATA_PATH = OUTPUT_DIR / "run_metadata.json"

RECEIPT_LINES = (
    "PANTRYPROOF TEST MART",
    "DATE: 2026-10-13",
    "MILK 2 x 5.50 11.00",
    "RICE 1 x 12.90 12.90",
    "TOTAL 23.90",
)

OCR_OPTIONS: dict[str, Any] = {
    "lang": "en",
    "ocr_version": "PP-OCRv6",
    "device": "cpu",
    # PaddlePaddle 3.3.1 has a known PIR/oneDNN CPU inference bug for these
    # models. Keep the installed versions unchanged and use the plain CPU path.
    "enable_mkldnn": False,
    "use_doc_orientation_classify": False,
    "use_doc_unwarping": False,
    "use_textline_orientation": False,
}


def load_font(size: int) -> tuple[ImageFont.FreeTypeFont, str]:
    """Load a readable font from stable Windows/Pillow candidates."""
    candidates = (
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("DejaVuSansMono.ttf"),
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size), str(candidate)
        except OSError:
            continue
    raise RuntimeError("No suitable TrueType font was found for the synthetic receipt.")


def create_synthetic_receipt(path: Path) -> str:
    """Create a high-contrast receipt image and return the font identifier."""
    image = Image.new("RGB", (1100, 700), "white")
    draw = ImageDraw.Draw(image)
    body_font, font_name = load_font(42)
    header_font, _ = load_font(48)

    draw.rectangle((24, 24, 1075, 675), outline="black", width=3)
    y = 70
    for index, line in enumerate(RECEIPT_LINES):
        font = header_font if index == 0 else body_font
        draw.text((70, y), line, fill="black", font=font)
        y += 112 if index == 0 else 98

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return font_name


def as_builtin(value: Any) -> Any:
    """Convert Paddle/NumPy-style values to plain JSON-compatible values."""
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, dict):
        return {key: as_builtin(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_builtin(item) for item in value]
    return value


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    font_name = create_synthetic_receipt(IMAGE_PATH)
    print(f"Synthetic receipt: {IMAGE_PATH}")

    print("Initializing PaddleOCR with:")
    print(json.dumps(OCR_OPTIONS, indent=2))
    ocr = PaddleOCR(**OCR_OPTIONS)

    try:
        # Export PaddleX's merged configuration so the resolved model names and
        # disabled optional preprocessing stages are recorded with the run.
        ocr.export_paddlex_config_to_yaml(CONFIG_PATH)
        effective_config = ocr._merged_paddlex_config  # Verified PaddleOCR 3.7 state.
        detection_model = effective_config["SubModules"]["TextDetection"]["model_name"]
        recognition_model = effective_config["SubModules"]["TextRecognition"]["model_name"]

        print(f"PaddleOCR version: {version('paddleocr')}")
        print(f"PaddlePaddle version: {paddle.__version__}")
        print(f"Paddle device: {paddle.device.get_device()}")
        print(f"Detection model: {detection_model}")
        print(f"Recognition model: {recognition_model}")

        # PaddleOCR 3.x returns one result object per input passed to predict().
        results = ocr.predict(str(IMAGE_PATH))
        if len(results) != 1:
            raise RuntimeError(f"Expected one OCR result, received {len(results)}.")

        result = results[0]
        texts = list(result.get("rec_texts", []))
        scores = list(result.get("rec_scores", []))
        polygons = list(result.get("rec_polys", result.get("dt_polys", [])))
        boxes = list(result.get("rec_boxes", []))

        print("\nRecognized regions:")
        region_count = max(len(texts), len(scores), len(polygons), len(boxes))
        for index in range(region_count):
            text = texts[index] if index < len(texts) else None
            score = scores[index] if index < len(scores) else None
            polygon = polygons[index] if index < len(polygons) else None
            box = boxes[index] if index < len(boxes) else None
            score_text = f"{float(score):.6f}" if score is not None else "n/a"
            print(f"[{index:02d}] text={text!r} confidence={score_text}")
            print(f"     polygon={as_builtin(polygon)}")
            print(f"     box={as_builtin(box)}")

        if not any(text and any(character.isalnum() for character in text) for text in texts):
            raise RuntimeError("OCR inference completed but produced no readable text.")

        result.save_to_json(str(RAW_OUTPUT_PATH))
        visualization_saved = False
        visualization_error = None
        try:
            result.save_to_img(str(VISUALIZATION_PATH))
            visualization_saved = VISUALIZATION_PATH.exists()
        except Exception as exc:  # Keep raw inference usable if visualization is unavailable.
            visualization_error = f"{type(exc).__name__}: {exc}"
            print(f"Visualization warning: {visualization_error}", file=sys.stderr)

        metadata = {
            "source_image": str(IMAGE_PATH),
            "synthetic_text": list(RECEIPT_LINES),
            "font": font_name,
            "packages": {
                "python": sys.version,
                "paddlepaddle": paddle.__version__,
                "paddleocr": version("paddleocr"),
                "paddlex": version("paddlex"),
                "pillow": version("pillow"),
            },
            "device": paddle.device.get_device(),
            "requested_ocr_options": OCR_OPTIONS,
            "resolved_models": {
                "text_detection": detection_model,
                "text_recognition": recognition_model,
            },
            "recognized_region_count": region_count,
            "recognized_texts": texts,
            "recognition_scores": as_builtin(scores),
            "recognition_polygons": as_builtin(polygons),
            "recognition_boxes": as_builtin(boxes),
            "raw_output": str(RAW_OUTPUT_PATH),
            "effective_config": str(CONFIG_PATH),
            "visualization": {
                "path": str(VISUALIZATION_PATH),
                "saved": visualization_saved,
                "error": visualization_error,
            },
        }
        METADATA_PATH.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        print(f"\nRaw OCR output: {RAW_OUTPUT_PATH}")
        print(f"Effective config: {CONFIG_PATH}")
        print(f"Run metadata: {METADATA_PATH}")
        print(f"Visualization saved: {visualization_saved} ({VISUALIZATION_PATH})")
        return 0
    finally:
        ocr.close()


if __name__ == "__main__":
    raise SystemExit(main())

"""Handwritten pages → Markdown, via a vision model on OpenRouter."""

import io
from pathlib import Path

from PIL import Image, ImageOps

from llm.llm_util import get_vision_response

MODEL = "anthropic/claude-sonnet-5.5"
PROMPT = Path(__file__).parent / "prompts" / "transcribe.jinja2"

# Phone photos are ~4000 px on the long edge; models downscale internally anyway,
# so sending that much only costs upload time. The vault keeps the original.
MAX_EDGE_PX = 2400
EXIF_ORIENTATION = 0x0112


def prepare(data: bytes, mime: str) -> tuple[bytes, str]:
    """Upright and shrink an image for the model; small, upright images pass through untouched."""
    image = Image.open(io.BytesIO(data))
    rotated = image.getexif().get(EXIF_ORIENTATION, 1) != 1
    if max(image.size) <= MAX_EDGE_PX and not rotated:
        return data, mime
    upright = ImageOps.exif_transpose(image)
    upright.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX))
    out = io.BytesIO()
    upright.convert("RGB").save(out, format="JPEG", quality=90)
    return out.getvalue(), "image/jpeg"


def _strip_fences(text: str) -> str:
    """Drop a ```markdown ... ``` wrapper if the model adds one despite the prompt."""
    lines = text.strip().splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        lines = lines[1:-1]
    return "\n".join(lines).strip()


def transcribe(pages: list[tuple[bytes, str]], caption: str | None = None,
               model: str = MODEL) -> str:
    """Transcribe all pages in one call, so text running across a page break stays whole."""
    images = [prepare(data, mime) for data, mime in pages]
    text = get_vision_response(str(PROMPT), {"pages": len(pages), "caption": caption or ""},
                               images, model_name=model)
    return _strip_fences(text)

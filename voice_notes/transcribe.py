"""Speech to text with Cactus Whistle, run locally on the CPU.

Whistle is a 17 MB model on the Needle engine (``cactus-needle``). The engine
library and weights are fetched from Hugging Face on first use and cached under
``~/.cactus_needle``/``~/.cache``. The model is loaded once per process and is not
thread-safe, so every call goes through one lock.
"""

import os
import threading

import numpy as np

from util.logging_util import setup_logger
from voice_notes.audio import chunks

# cactus-needle sends anonymous usage counts unless told not to. Set before the
# first import of needle, which happens lazily in _model().
os.environ.setdefault("NEEDLE_TELEMETRY", "0")

logger = setup_logger(__name__)

MODEL_NAME = "Cactus-Compute/whistle"
LANGUAGE = "en"

_lock = threading.Lock()
_whistle = None


def _model():
    global _whistle
    if _whistle is None:
        from needle.agent.whistle import Whistle

        logger.info("Loading Whistle model")
        _whistle = Whistle()
    return _whistle


def transcribe(samples: np.ndarray) -> str:
    """16 kHz mono float32 samples -> English text. Blocking; call off the event loop."""
    with _lock:
        model = _model()
        texts = [model.transcribe(chunk, language=LANGUAGE)["text"].strip()
                 for chunk in chunks(samples)]
    return " ".join(t for t in texts if t)

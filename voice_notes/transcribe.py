"""Speech to text with Whisper large-v3-turbo, run locally on the CPU.

faster-whisper (CTranslate2, int8) downloads the weights from Hugging Face on
first load and caches them under ``~/.cache/huggingface``. Loading takes ~20 s
and ~1.5 GB of RAM, so the bot loads it once at startup (:func:`load`) rather
than on the first note. Whisper handles audio of any length itself, and the VAD
filter skips silence, which is where Whisper otherwise tends to invent text.

Picked over Cactus Whistle after it heard "verisimilitude" as "very similar to"
on real notes; turbo was the only model tried that got it in and out of context.
"""

import threading

import numpy as np

from util.logging_util import setup_logger

logger = setup_logger(__name__)

MODEL_NAME = "large-v3-turbo"
# What notes record in their frontmatter, so a later re-run knows what made them.
MODEL_LABEL = f"whisper-{MODEL_NAME}"
LANGUAGE = "en"

_lock = threading.Lock()
_whisper = None


def _model():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel

        logger.info(f"Loading Whisper {MODEL_NAME}")
        _whisper = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
        logger.info(f"Whisper {MODEL_NAME} loaded")
    return _whisper


def load() -> None:
    """Load the model now, so the first voice note doesn't wait for it. Blocking."""
    with _lock:
        _model()


def transcribe(samples: np.ndarray) -> str:
    """16 kHz mono float32 samples -> English text. Blocking; call off the event loop."""
    if len(samples) == 0:
        return ""
    with _lock:
        # The default VAD padding clipped a lone "verisimilitude" to
        # "Verisimilar-tude"; a full second each side keeps word edges intact.
        segments, _ = _model().transcribe(
            samples, language=LANGUAGE, beam_size=5,
            vad_filter=True, vad_parameters={"speech_pad_ms": 1000},
        )
        # segments is a lazy generator: the decoding happens while it's consumed,
        # so that has to stay inside the lock too.
        return " ".join(s.text.strip() for s in segments if s.text.strip())

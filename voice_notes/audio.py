"""Decoding Telegram voice notes into samples for the model.

Telegram sends voice notes as Opus in an OGG container. PyAV decodes that with
the ffmpeg libraries bundled in its wheel, so the server needs no ffmpeg install.
(faster-whisper's own ``decode_audio`` passes an option newer PyAV rejects, so
the model is always handed samples, never a file.)
"""

from io import BytesIO

import av
import numpy as np

SAMPLE_RATE = 16_000


def decode(audio: bytes) -> np.ndarray:
    """Any audio file's bytes -> 16 kHz mono float32 samples in [-1, 1]."""
    pieces = []
    with av.open(BytesIO(audio)) as container:
        resampler = av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE)
        for frame in container.decode(audio=0):
            pieces.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(frame))
        pieces.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(None))
    if not pieces:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(pieces).astype(np.float32)


def duration_seconds(samples: np.ndarray) -> float:
    return len(samples) / SAMPLE_RATE

"""Decoding Telegram voice notes and cutting them into model-sized pieces.

Telegram sends voice notes as Opus in an OGG container. PyAV decodes that with
the ffmpeg libraries bundled in its wheel, so the server needs no ffmpeg install.
"""

from io import BytesIO

import av
import numpy as np

SAMPLE_RATE = 16_000

# Whistle refuses anything over 30 s in one pass. Cuts land in the quietest
# stretch of the last few seconds before that limit, so they fall between words
# rather than through one.
MAX_CHUNK_SECONDS = 30.0
SEARCH_SECONDS = 5.0
WINDOW_SECONDS = 0.1


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


def _quietest_cut(samples: np.ndarray, start: int, end: int) -> int:
    """Index in [start, end) at the centre of the lowest-energy window."""
    window = int(WINDOW_SECONDS * SAMPLE_RATE)
    region = samples[start:end]
    n_windows = len(region) // window
    if n_windows == 0:
        return end
    energy = (region[: n_windows * window].reshape(n_windows, window) ** 2).mean(axis=1)
    return start + int(energy.argmin()) * window + window // 2


def chunks(samples: np.ndarray) -> list[np.ndarray]:
    """Split samples into consecutive pieces of at most MAX_CHUNK_SECONDS.

    The pieces concatenate back to exactly the input; nothing is dropped or
    overlapped, so no words are lost or doubled at the seams.
    """
    max_len = int(MAX_CHUNK_SECONDS * SAMPLE_RATE)
    search = int(SEARCH_SECONDS * SAMPLE_RATE)
    out = []
    pos = 0
    while len(samples) - pos > max_len:
        cut = _quietest_cut(samples, pos + max_len - search, pos + max_len)
        out.append(samples[pos:cut])
        pos = cut
    if pos < len(samples):
        out.append(samples[pos:])
    return out

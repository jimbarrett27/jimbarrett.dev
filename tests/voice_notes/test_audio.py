"""Tests for voice_notes.audio -- decoding and cutting audio for the model."""

from io import BytesIO

import av
import numpy as np
import pytest

from voice_notes.audio import SAMPLE_RATE, decode, duration_seconds


def _opus_ogg(samples: np.ndarray) -> bytes:
    """Encode 16 kHz float samples the way Telegram sends voice notes."""
    buf = BytesIO()
    with av.open(buf, "w", format="ogg") as container:
        stream = container.add_stream("libopus", rate=48000, layout="mono")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)
        frame = av.AudioFrame.from_ndarray(
            (samples * 32767).astype(np.int16).reshape(1, -1), format="s16", layout="mono")
        frame.rate = SAMPLE_RATE
        for f in resampler.resample(frame):
            for packet in stream.encode(f):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return buf.getvalue()


def _tone(seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def test_decode_opus_ogg_to_16k_mono():
    samples = decode(_opus_ogg(_tone(2.0)))
    assert samples.dtype == np.float32
    assert samples.ndim == 1
    # Opus pre-skip/padding shifts the length by a few ms at most.
    assert duration_seconds(samples) == pytest.approx(2.0, abs=0.05)
    assert np.abs(samples).max() <= 1.0

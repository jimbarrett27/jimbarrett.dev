"""Tests for voice_notes.audio -- decoding and cutting audio for the model."""

from io import BytesIO

import av
import numpy as np
import pytest

from voice_notes.audio import MAX_CHUNK_SECONDS, SAMPLE_RATE, chunks, decode, duration_seconds


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


def test_short_audio_is_one_chunk():
    samples = _tone(12.0)
    [only] = chunks(samples)
    assert np.array_equal(only, samples)


def test_empty_audio_has_no_chunks():
    assert chunks(np.zeros(0, dtype=np.float32)) == []


@pytest.mark.parametrize("seconds", [30.0, 30.5, 61.0, 125.3])
def test_chunks_fit_the_model_and_lose_nothing(seconds):
    samples = np.random.default_rng(0).uniform(-0.5, 0.5, int(seconds * SAMPLE_RATE)).astype(np.float32)
    pieces = chunks(samples)
    assert all(len(p) <= MAX_CHUNK_SECONDS * SAMPLE_RATE for p in pieces)
    assert all(len(p) > 0 for p in pieces)
    assert np.array_equal(np.concatenate(pieces), samples)


def test_cut_lands_in_the_pause():
    # 27 s of speech-like noise, a 0.5 s pause, then more: the cut should be in the pause.
    rng = np.random.default_rng(1)
    loud = lambda s: rng.uniform(-0.5, 0.5, int(s * SAMPLE_RATE)).astype(np.float32)
    pause = np.zeros(int(0.5 * SAMPLE_RATE), dtype=np.float32)
    samples = np.concatenate([loud(27.0), pause, loud(20.0)])
    first = chunks(samples)[0]
    assert 27.0 <= duration_seconds(first) <= 27.5

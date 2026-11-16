"""Pure audio helpers: WAV encode/decode, resampling, level metering and chunking."""

from __future__ import annotations

import io
import wave

import numpy as np


def to_int16(samples: np.ndarray) -> np.ndarray:
    samples = np.asarray(samples)
    if samples.dtype == np.int16:
        return samples
    clipped = np.clip(samples.astype(np.float32), -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16)


def to_float32(samples: np.ndarray) -> np.ndarray:
    samples = np.asarray(samples)
    if samples.dtype == np.int16:
        return samples.astype(np.float32) / 32768.0
    return samples.astype(np.float32)


def encode_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Encode mono samples (float32 in [-1, 1] or int16) as 16-bit PCM WAV bytes."""
    pcm = to_int16(np.asarray(samples).reshape(-1))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def decode_wav(data: bytes) -> tuple[np.ndarray, int]:
    """Decode 16-bit PCM WAV bytes to (mono float32 samples, sample_rate)."""
    with wave.open(io.BytesIO(data), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError("only 16-bit PCM WAV is supported")
        channels = w.getnchannels()
        rate = w.getframerate()
        frames = w.readframes(w.getnframes())
    pcm = np.frombuffer(frames, dtype="<i2")
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return to_float32(pcm), rate


def resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Band-limited (FFT) resampling.

    Unlike linear interpolation this removes content above the new Nyquist
    frequency instead of aliasing it, which keeps consonants crisp for STT.
    """
    samples = to_float32(samples).reshape(-1)
    if src_rate == dst_rate or samples.size == 0:
        return samples
    n_in = samples.size
    n_out = int(round(n_in * dst_rate / src_rate))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    spectrum = np.fft.rfft(samples)
    n_bins = n_out // 2 + 1
    if n_bins <= spectrum.size:
        spectrum = spectrum[:n_bins]
    else:
        spectrum = np.concatenate([spectrum, np.zeros(n_bins - spectrum.size, spectrum.dtype)])
    out = np.fft.irfft(spectrum, n=n_out) * (n_out / n_in)
    return out.astype(np.float32)


def trim_silence(samples: np.ndarray, sample_rate: int, threshold: float = 0.01,
                 pad_seconds: float = 0.2, window_seconds: float = 0.02) -> np.ndarray:
    """Remove leading/trailing silence, keeping ``pad_seconds`` of margin.

    ``threshold`` is relative to the loudest window (with a small absolute floor),
    so it adapts to quiet and loud microphones alike. Returns an empty array if
    the clip is entirely silent.
    """
    samples = to_float32(samples).reshape(-1)
    win = max(1, int(window_seconds * sample_rate))
    n_win = samples.size // win
    if n_win == 0:
        return samples
    rms = np.sqrt(np.square(samples[: n_win * win]).reshape(n_win, win).mean(axis=1))
    peak = float(rms.max())
    if peak < 1e-4:
        return samples[:0]
    loud = np.nonzero(rms >= max(peak * threshold * 10, 0.002))[0]
    pad = int(pad_seconds * sample_rate)
    start = max(0, int(loud[0]) * win - pad)
    end = min(samples.size, (int(loud[-1]) + 1) * win + pad)
    return samples[start:end]


def normalize(samples: np.ndarray, target_peak: float = 0.9, max_gain: float = 8.0) -> np.ndarray:
    """Scale quiet audio up towards ``target_peak`` (never attenuates, never clips)."""
    samples = to_float32(samples).reshape(-1)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak <= 0:
        return samples
    gain = min(max_gain, target_peak / peak)
    if gain <= 1.0:
        return samples
    return (samples * gain).astype(np.float32)


def rms_level(samples: np.ndarray) -> float:
    """Root-mean-square level in [0, 1] for float samples."""
    samples = to_float32(samples).reshape(-1)
    if samples.size == 0:
        return 0.0
    return float(min(1.0, np.sqrt(np.mean(np.square(samples)))))


def split_chunks(
    samples: np.ndarray,
    sample_rate: int,
    chunk_seconds: float,
    search_seconds: float = 2.0,
    window_seconds: float = 0.05,
) -> list[np.ndarray]:
    """Split audio into chunks of at most ``chunk_seconds``.

    Each cut is placed at the quietest short window within the last
    ``search_seconds`` before the limit, so words are rarely cut in half.
    """
    samples = np.asarray(samples).reshape(-1)
    max_len = int(chunk_seconds * sample_rate)
    if max_len <= 0 or samples.size <= max_len:
        return [samples] if samples.size else []

    win = max(1, int(window_seconds * sample_rate))
    search = min(int(search_seconds * sample_rate), max_len // 2)
    chunks = []
    start = 0
    while samples.size - start > max_len:
        hard_end = start + max_len
        lo = hard_end - search
        region = to_float32(samples[lo:hard_end])
        n_win = region.size // win
        cut = hard_end
        if n_win > 1:
            energy = np.square(region[: n_win * win]).reshape(n_win, win).mean(axis=1)
            cut = lo + int(np.argmin(energy)) * win + win // 2
        chunks.append(samples[start:cut])
        start = cut
    chunks.append(samples[start:])
    return [c for c in chunks if c.size]

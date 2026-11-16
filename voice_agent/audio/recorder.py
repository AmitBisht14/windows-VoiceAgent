"""Microphone capture from the system default input device."""

from __future__ import annotations

import logging
import threading

import numpy as np

from .wav import encode_wav, normalize, resample, rms_level, trim_silence

log = logging.getLogger(__name__)


class RecorderError(RuntimeError):
    pass


class AudioRecorder:
    """Records mono audio from the default microphone.

    The stream is opened at ``sample_rate`` (16 kHz) when the device supports
    it, otherwise at the device's native rate and resampled on stop.
    """

    def __init__(self, sample_rate: int = 16000, min_duration: float = 0.3,
                 max_duration: float = 300.0, sd_module=None):
        self.sample_rate = sample_rate
        self.min_duration = min_duration
        self.max_duration = max_duration
        self._sd = sd_module
        self._stream = None
        self._frames: list[np.ndarray] = []
        self._n_samples = 0
        self._stream_rate = sample_rate
        self._lock = threading.Lock()
        self._level = 0.0

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    @property
    def level(self) -> float:
        """Most recent input RMS level in [0, 1]."""
        return self._level

    def _sounddevice(self):
        if self._sd is None:
            try:
                import sounddevice as sd  # lazy: needs PortAudio
            except OSError as exc:  # pragma: no cover - platform specific
                raise RecorderError(f"Audio backend unavailable: {exc}") from exc
            self._sd = sd
        return self._sd

    def _callback(self, indata, frames, time_info, status):  # sounddevice callback thread
        if status:
            log.debug("Audio status: %s", status)
        mono = np.array(indata[:, 0] if indata.ndim > 1 else indata, dtype=np.float32, copy=True)
        with self._lock:
            if self._n_samples < self.max_duration * self._stream_rate:
                self._frames.append(mono)
                self._n_samples += mono.size
        self._level = rms_level(mono)

    def start(self) -> None:
        if self._stream is not None:
            return
        sd = self._sounddevice()
        with self._lock:
            self._frames = []
            self._n_samples = 0
        self._level = 0.0
        last_exc = None
        rates = [self.sample_rate]
        try:
            default_rate = int(sd.query_devices(kind="input")["default_samplerate"])
            if default_rate not in rates:
                rates.append(default_rate)
        except Exception as exc:  # no input device
            raise RecorderError(f"No default microphone found: {exc}") from exc
        for rate in rates:
            try:
                stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                        callback=self._callback)
                self._stream_rate = rate
                stream.start()
                self._stream = stream
                return
            except Exception as exc:
                last_exc = exc
                log.info("Could not open microphone at %s Hz: %s", rate, exc)
        raise RecorderError(f"Could not open the default microphone: {last_exc}")

    def stop(self) -> bytes | None:
        """Stop recording. Returns 16 kHz mono WAV bytes, or None if too short."""
        stream, self._stream = self._stream, None
        if stream is None:
            return None
        try:
            stream.stop()
            stream.close()
        except Exception:
            log.exception("Error closing audio stream")
        self._level = 0.0
        with self._lock:
            frames, self._frames = self._frames, []
            self._n_samples = 0
        if not frames:
            return None
        audio = np.concatenate(frames)
        audio = resample(audio, self._stream_rate, self.sample_rate)
        if audio.size < self.min_duration * self.sample_rate:
            log.info("Recording too short (%.2fs), discarding", audio.size / self.sample_rate)
            return None
        recorded = audio.size / self.sample_rate
        audio = trim_silence(audio, self.sample_rate)
        if audio.size < self.min_duration * self.sample_rate:
            log.info("Recording (%.2fs) contained no speech, discarding", recorded)
            return None
        audio = normalize(audio)
        log.info("Captured %.2fs of audio (%.2fs after trimming)", recorded,
                 audio.size / self.sample_rate)
        return encode_wav(audio, self.sample_rate)

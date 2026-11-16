"""Local speech-to-text with NVIDIA Parakeet TDT 0.6B v2 on ONNX Runtime.

Parakeet TDT 0.6B v2 is an English-only open-weight (CC-BY-4.0) speech
recognition model. It tops the Open ASR leaderboard for its size, outputs
punctuation and capitalization, and with int8 weights (~630 MB) transcribes
far faster than real time on an ordinary CPU, with no GPU and no server.

The ONNX export is downloaded once from Hugging Face into the app's models
folder; afterwards the app runs fully offline.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

from .base import HealthStatus, TranscriptionClient
from ..audio.wav import decode_wav, resample, rms_level, split_chunks

log = logging.getLogger(__name__)

TARGET_RATE = 16000
DEFAULT_MODEL = "nemo-parakeet-tdt-0.6b-v2"
_READY_MARKER = ".voice-agent-ready"


class ModelLoadError(RuntimeError):
    pass


def _default_loader(model: str, quantization: str | None, cache_dir: Path, threads: int):
    marker = cache_dir / f"{model}{'-' + quantization if quantization else ''}{_READY_MARKER}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Must be set before huggingface_hub is imported. Once the model is complete,
    # never contact the network again (no update checks, fully offline).
    os.environ["HF_HUB_CACHE"] = str(cache_dir)
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    if marker.exists():
        os.environ["HF_HUB_OFFLINE"] = "1"

    import onnx_asr
    import onnxruntime as ort

    opts = ort.SessionOptions()
    if threads > 0:
        opts.intra_op_num_threads = threads
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    model_obj = onnx_asr.load_model(model, quantization=quantization or None, sess_options=opts,
                                    providers=["CPUExecutionProvider"])
    marker.touch()
    return model_obj


class ParakeetTranscriptionClient(TranscriptionClient):
    def __init__(self, model: str = DEFAULT_MODEL, quantization: str | None = "int8",
                 cache_dir: Path | None = None, chunk_seconds: float = 30.0,
                 cpu_threads: int = 0, silence_threshold: float = 0.004,
                 loader: Callable | None = None):
        self.model_name = model
        self.quantization = quantization or None
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "voice-agent"
        self.chunk_seconds = chunk_seconds
        self.cpu_threads = cpu_threads
        self.silence_threshold = silence_threshold
        self._loader = loader or _default_loader
        self._model = None
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, cfg) -> "ParakeetTranscriptionClient":
        from ..config import models_dir
        return cls(model=cfg.parakeet_model, quantization=cfg.parakeet_quantization,
                   cache_dir=models_dir(), chunk_seconds=cfg.parakeet_chunk_seconds,
                   cpu_threads=cfg.cpu_threads, silence_threshold=cfg.silence_threshold)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def _get_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    started = time.perf_counter()
                    log.info("Loading speech model %s (%s)", self.model_name,
                             self.quantization or "fp32")
                    try:
                        self._model = self._loader(self.model_name, self.quantization,
                                                   self.cache_dir, self.cpu_threads)
                    except ImportError as exc:
                        raise ModelLoadError(
                            "Speech engine not installed. Run: pip install \"onnx-asr[cpu,hub]\""
                        ) from exc
                    except Exception as exc:
                        raise ModelLoadError(
                            f"Could not load speech model {self.model_name}: {exc}. The first run "
                            "needs internet access to download it (~630 MB).") from exc
                    log.info("Speech model loaded in %.1fs", time.perf_counter() - started)
        return self._model

    def warm_up(self) -> None:
        model = self._get_model()
        model.recognize(np.zeros(TARGET_RATE // 2, dtype=np.float32), sample_rate=TARGET_RATE)

    def health_check(self) -> HealthStatus:
        try:
            self.warm_up()
        except ModelLoadError as exc:
            return HealthStatus(False, str(exc))
        return HealthStatus(True, "Speech model ready (Parakeet TDT 0.6B v2)")

    def transcribe(self, audio_bytes: bytes) -> str:
        samples, rate = decode_wav(audio_bytes)
        if rate != TARGET_RATE:
            samples = resample(samples, rate, TARGET_RATE)
        model = self._get_model()
        parts = []
        for chunk in split_chunks(samples, TARGET_RATE, self.chunk_seconds):
            if rms_level(chunk) < self.silence_threshold:
                continue
            text = model.recognize(np.ascontiguousarray(chunk, dtype=np.float32),
                                   sample_rate=TARGET_RATE)
            text = " ".join(str(text or "").split())
            if text:
                parts.append(text)
        return " ".join(parts)

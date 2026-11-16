"""Speech-to-text through a local Ollama server.

Default model: ``gemma4:e2b`` - Google's Gemma 4 "effective 2B" open-weight model,
which has a native audio encoder. It is the smallest Ollama model that accepts
audio, runs on CPU-only or low-VRAM machines, and transcribes English well.

Ollama has no dedicated audio field yet (ollama/ollama#11798). Audio is passed
as a base64 16 kHz mono 16-bit WAV in the message's ``images`` list; Ollama
detects the RIFF/WAVE header and routes it to the audio encoder. The model
handles roughly 30 s per request, so long recordings are split into chunks.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .base import TranscriptionClient
from ..audio.wav import decode_wav, encode_wav, resample, rms_level, split_chunks

log = logging.getLogger(__name__)

TARGET_RATE = 16000
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

_PREFIX_RE = re.compile(r"^\s*(?:here(?:'s| is) the transcription:?|transcription:|transcript:)\s*",
                        re.IGNORECASE)
_THINK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_NO_SPEECH = {"", "[no speech]", "(no speech)", "[silence]", "(silence)", "no speech", "[blank_audio]"}


class OllamaError(RuntimeError):
    """A user-facing problem talking to Ollama."""


@dataclass
class HealthStatus:
    ok: bool
    message: str
    version: str | None = None


def clean_transcript(text: str) -> str:
    text = _THINK_RE.sub("", text or "").strip()
    text = _PREFIX_RE.sub("", text).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'`":
        text = text[1:-1].strip()
    if text.lower() in _NO_SPEECH:
        return ""
    return re.sub(r"\s+", " ", text)


def _model_matches(wanted: str, available: str) -> bool:
    def norm(name: str) -> str:
        return name if ":" in name else f"{name}:latest"
    return norm(wanted) == norm(available)


class OllamaTranscriptionClient(TranscriptionClient):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma4:e2b",
                 prompt: str = "Transcribe this audio.", chunk_seconds: float = 20.0,
                 num_ctx: int = 8192, timeout: float = 120.0, keep_alive: str = "10m",
                 api: str = "native", silence_threshold: float = 0.004, opener=None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.prompt = prompt
        self.chunk_seconds = chunk_seconds
        self.num_ctx = num_ctx
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.api = api
        self.silence_threshold = silence_threshold
        if opener is None:
            host = urllib.parse.urlparse(self.base_url).hostname or ""
            # Never route a local Ollama through a system HTTP proxy.
            handlers = [urllib.request.ProxyHandler({})] if host in LOCAL_HOSTS else []
            opener = urllib.request.build_opener(*handlers)
        self._opener = opener

    @classmethod
    def from_config(cls, cfg) -> "OllamaTranscriptionClient":
        return cls(base_url=cfg.ollama_url, model=cfg.model, prompt=cfg.prompt,
                   chunk_seconds=cfg.chunk_seconds, num_ctx=cfg.num_ctx,
                   timeout=cfg.request_timeout, keep_alive=cfg.keep_alive,
                   api=cfg.ollama_api, silence_threshold=cfg.silence_threshold)

    # ------------------------------------------------------------------ HTTP
    def _request(self, method: str, path: str, payload: dict | None = None,
                 timeout: float | None = None) -> dict:
        url = self.base_url + path
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with self._opener.open(req, timeout=timeout or self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", "")
            except Exception:
                pass
            if exc.code == 404 and "not found" in detail.lower():
                raise OllamaError(f"Model '{self.model}' is not installed. "
                                  f"Run: ollama pull {self.model}") from exc
            raise OllamaError(f"Ollama returned HTTP {exc.code}: {detail or exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise OllamaError(f"Cannot reach Ollama at {self.base_url} ({reason}). "
                              "Is Ollama running?") from exc
        try:
            return json.loads(body) if body else {}
        except ValueError as exc:
            raise OllamaError("Ollama sent an invalid response") from exc

    # ---------------------------------------------------------------- health
    def health_check(self) -> HealthStatus:
        try:
            version = self._request("GET", "/api/version", timeout=5).get("version")
            tags = self._request("GET", "/api/tags", timeout=5)
        except OllamaError as exc:
            return HealthStatus(False, str(exc))
        names = [m.get("name") or m.get("model") or "" for m in tags.get("models", [])]
        if not any(_model_matches(self.model, n) for n in names):
            return HealthStatus(False, f"Ollama is running but '{self.model}' is not installed. "
                                       f"Run: ollama pull {self.model}", version)
        return HealthStatus(True, f"Ollama {version or ''} ready with {self.model}".replace("  ", " "),
                            version)

    # ---------------------------------------------------------- transcribe
    def _payload_native(self, wav_b64: str) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": self.prompt, "images": [wav_b64]}],
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": 0, "num_ctx": self.num_ctx},
        }

    def _payload_openai(self, wav_b64: str) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "input_audio", "input_audio": {"data": wav_b64, "format": "wav"}},
                {"type": "text", "text": self.prompt},
            ]}],
            "temperature": 0,
            "stream": False,
        }

    def _transcribe_chunk(self, wav_bytes: bytes) -> str:
        wav_b64 = base64.b64encode(wav_bytes).decode("ascii")
        if self.api == "openai":
            resp = self._request("POST", "/v1/chat/completions", self._payload_openai(wav_b64))
            choices = resp.get("choices") or [{}]
            text = (choices[0].get("message") or {}).get("content", "")
        else:
            resp = self._request("POST", "/api/chat", self._payload_native(wav_b64))
            text = (resp.get("message") or {}).get("content", "")
        return clean_transcript(text)

    def transcribe(self, audio_bytes: bytes) -> str:
        samples, rate = decode_wav(audio_bytes)
        if rate != TARGET_RATE:
            samples = resample(samples, rate, TARGET_RATE)
        parts = []
        for chunk in split_chunks(samples, TARGET_RATE, self.chunk_seconds):
            if rms_level(chunk) < self.silence_threshold:
                log.debug("Skipping silent chunk (%.1fs)", chunk.size / TARGET_RATE)
                continue
            text = self._transcribe_chunk(encode_wav(chunk, TARGET_RATE))
            if text:
                parts.append(text)
        return " ".join(parts).strip()

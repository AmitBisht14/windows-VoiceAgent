"""Persistent user settings stored as JSON.

Location: ``%APPDATA%\\VoiceAgent\\config.json`` on Windows, otherwise
``$XDG_CONFIG_HOME/voice-agent/config.json`` (default ``~/.config``).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_PROMPT = (
    "Transcribe this audio exactly as spoken, in English. Add correct punctuation and "
    "capitalization. Output only the transcription text, with no preamble, labels, "
    "quotes or commentary. If there is no speech, output nothing."
)


@dataclass
class Config:
    # Hotkey
    hotkey: str = "ctrl+win"
    hotkey_mode: str = "hold"  # "hold" (push-to-talk) or "toggle"

    # Speech-to-text engine: "parakeet" (local ONNX, default) or "ollama".
    stt_engine: str = "parakeet"

    # Parakeet (NVIDIA Parakeet TDT 0.6B v2, English, run with ONNX Runtime)
    parakeet_model: str = "nemo-parakeet-tdt-0.6b-v2"
    parakeet_quantization: str = "int8"  # "int8" (fast, ~630 MB) or "" for full precision
    parakeet_chunk_seconds: float = 30.0
    cpu_threads: int = 0  # 0 = let ONNX Runtime choose

    # Ollama (optional engine; needs an audio-capable model such as gemma4:e2b)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:e2b"
    # "native" = POST /api/chat with the WAV in "images" (works with gemma4 today);
    # "openai" = POST /v1/chat/completions with an "input_audio" content part.
    ollama_api: str = "native"
    prompt: str = DEFAULT_PROMPT
    chunk_seconds: float = 20.0
    num_ctx: int = 8192
    request_timeout: float = 120.0
    keep_alive: str = "10m"
    silence_threshold: float = 0.004  # chunks quieter than this RMS are skipped

    # Audio
    sample_rate: int = 16000
    min_duration: float = 0.3
    tail_ms: int = 250  # keep recording briefly after the hotkey is released
    max_duration: float = 300.0

    # Text injection
    restore_clipboard: bool = True
    append_space: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        known = {f.name: f for f in fields(cls)}
        defaults = cls()
        kwargs = {}
        data = dict(data or {})
        if "model" in data and "ollama_model" not in data:  # pre-Parakeet config files
            data["ollama_model"] = data.pop("model")
        data.pop("model", None)
        for key, value in data.items():
            f = known.get(key)
            if f is None:
                log.warning("Ignoring unknown config key %r", key)
                continue
            default_value = getattr(defaults, key)
            try:
                if isinstance(default_value, bool):
                    if not isinstance(value, bool):
                        raise TypeError
                elif isinstance(default_value, (int, float)):
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise TypeError
                    value = type(default_value)(value)
                elif isinstance(default_value, str) and not isinstance(value, str):
                    raise TypeError
            except (TypeError, ValueError):
                log.warning("Invalid value for %r, using default", key)
                continue
            kwargs[key] = value
        cfg = cls(**kwargs)
        if cfg.hotkey_mode not in ("hold", "toggle"):
            log.warning("Invalid hotkey_mode %r, using 'hold'", cfg.hotkey_mode)
            cfg.hotkey_mode = "hold"
        if cfg.stt_engine not in ("parakeet", "ollama"):
            log.warning("Invalid stt_engine %r, using 'parakeet'", cfg.stt_engine)
            cfg.stt_engine = "parakeet"
        if cfg.ollama_api not in ("native", "openai"):
            log.warning("Invalid ollama_api %r, using 'native'", cfg.ollama_api)
            cfg.ollama_api = "native"
        return cfg

    def to_dict(self) -> dict:
        return asdict(self)


def config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "VoiceAgent"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "voice-agent"


def models_dir() -> Path:
    """Where downloaded speech models are cached (kept out of roaming profiles)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "VoiceAgent" / "models"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "voice-agent" / "models"


def config_path() -> Path:
    return config_dir() / "config.json"


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        cfg = Config()
        try:
            save_config(cfg, path)
        except OSError:
            log.exception("Could not write default config to %s", path)
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config root must be an object")
    except (OSError, ValueError):
        log.exception("Could not read config %s, using defaults", path)
        return Config()
    return Config.from_dict(data)


def save_config(cfg: Config, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")

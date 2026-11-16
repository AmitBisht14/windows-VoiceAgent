from .base import HealthStatus, TranscriptionClient


def create_client(cfg) -> TranscriptionClient:
    """Build the speech-to-text client selected by ``cfg.stt_engine``."""
    if cfg.stt_engine == "ollama":
        from .ollama import OllamaTranscriptionClient
        return OllamaTranscriptionClient.from_config(cfg)
    from .parakeet import ParakeetTranscriptionClient
    return ParakeetTranscriptionClient.from_config(cfg)


__all__ = ["HealthStatus", "TranscriptionClient", "create_client"]

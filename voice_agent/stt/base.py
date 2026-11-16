from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class HealthStatus:
    ok: bool
    message: str
    version: str | None = None


class TranscriptionClient(ABC):
    @abstractmethod
    def transcribe(self, audio_bytes: bytes) -> str:
        ...

    def health_check(self) -> HealthStatus:
        return HealthStatus(True, "ready")

    def warm_up(self) -> None:
        """Load models / open connections ahead of the first dictation."""

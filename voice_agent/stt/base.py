from abc import ABC, abstractmethod


class TranscriptionClient(ABC):
    @abstractmethod
    def transcribe(self, audio_bytes: bytes) -> str:
        ...

from .base import TranscriptionClient


class MockTranscriptionClient(TranscriptionClient):
    def transcribe(self, audio_bytes: bytes) -> str:
        return "[mock transcription]"

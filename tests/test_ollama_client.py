import base64
import io
import json
import urllib.error

import numpy as np
import pytest

from voice_agent.audio.wav import encode_wav
from voice_agent.config import Config
from voice_agent.stt.ollama import OllamaError, OllamaTranscriptionClient, clean_transcript


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self, handler):
        self.handler = handler
        self.requests = []

    def open(self, req, timeout=None):
        payload = json.loads(req.data) if req.data else None
        self.requests.append((req.get_method(), req.full_url, payload))
        result = self.handler(req.full_url, payload)
        if isinstance(result, Exception):
            raise result
        return FakeResponse(json.dumps(result).encode())


def speech(seconds, sr=16000):
    t = np.arange(int(seconds * sr)) / sr
    return encode_wav(0.3 * np.sin(2 * np.pi * 220 * t), sr)


def test_native_request_shape_and_result():
    opener = FakeOpener(lambda url, p: {"message": {"content": " Hello world. "}})
    client = OllamaTranscriptionClient(opener=opener, prompt="P")
    assert client.transcribe(speech(2)) == "Hello world."
    method, url, payload = opener.requests[0]
    assert url == "http://localhost:11434/api/chat"
    assert payload["model"] == "gemma4:e2b"
    assert payload["stream"] is False
    assert payload["options"] == {"temperature": 0, "num_ctx": 8192}
    msg = payload["messages"][0]
    assert msg["content"] == "P"
    wav = base64.b64decode(msg["images"][0])
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"


def test_openai_request_shape():
    opener = FakeOpener(lambda url, p: {"choices": [{"message": {"content": "Hi."}}]})
    client = OllamaTranscriptionClient(opener=opener, api="openai")
    assert client.transcribe(speech(1)) == "Hi."
    _, url, payload = opener.requests[0]
    assert url.endswith("/v1/chat/completions")
    parts = payload["messages"][0]["content"]
    assert parts[0]["type"] == "input_audio" and parts[0]["input_audio"]["format"] == "wav"
    assert parts[1]["type"] == "text"


def test_long_audio_is_chunked_and_joined():
    replies = iter(["First part.", "Second part."])
    opener = FakeOpener(lambda url, p: {"message": {"content": next(replies)}})
    client = OllamaTranscriptionClient(opener=opener, chunk_seconds=20)
    assert client.transcribe(speech(35)) == "First part. Second part."
    assert len(opener.requests) == 2


def test_silence_is_skipped():
    opener = FakeOpener(lambda url, p: {"message": {"content": "hallucination"}})
    client = OllamaTranscriptionClient(opener=opener)
    assert client.transcribe(encode_wav(np.zeros(16000), 16000)) == ""
    assert opener.requests == []


def test_resamples_other_rates():
    opener = FakeOpener(lambda url, p: {"message": {"content": "ok"}})
    client = OllamaTranscriptionClient(opener=opener)
    client.transcribe(speech(1, sr=48000))
    wav = base64.b64decode(opener.requests[0][2]["messages"][0]["images"][0])
    assert int.from_bytes(wav[24:28], "little") == 16000


def test_model_not_found_error():
    def handler(url, p):
        body = io.BytesIO(json.dumps({"error": "model 'gemma4:e2b' not found"}).encode())
        return urllib.error.HTTPError(url, 404, "Not Found", {}, body)
    client = OllamaTranscriptionClient(opener=FakeOpener(handler))
    with pytest.raises(OllamaError, match="ollama pull gemma4:e2b"):
        client.transcribe(speech(1))


def test_unreachable_error():
    client = OllamaTranscriptionClient(
        opener=FakeOpener(lambda u, p: urllib.error.URLError("refused")))
    with pytest.raises(OllamaError, match="Is Ollama running"):
        client.transcribe(speech(1))


def test_health_check():
    def handler(url, p):
        if url.endswith("/api/version"):
            return {"version": "0.30.4"}
        return {"models": [{"name": "gemma4:e2b"}, {"name": "llama3:latest"}]}
    status = OllamaTranscriptionClient(opener=FakeOpener(handler)).health_check()
    assert status.ok and status.version == "0.30.4"

    missing = OllamaTranscriptionClient(model="gemma4:e4b", opener=FakeOpener(handler)).health_check()
    assert not missing.ok and "ollama pull gemma4:e4b" in missing.message


def test_from_config():
    client = OllamaTranscriptionClient.from_config(Config(ollama_model="x:y", ollama_url="http://h:1/"))
    assert client.model == "x:y" and client.base_url == "http://h:1"


@pytest.mark.parametrize("raw,expected", [
    ('"Hello there."', "Hello there."),
    ("Transcription: Hello", "Hello"),
    ("Here is the transcription: Hi", "Hi"),
    ("<think>hmm</think>Okay.", "Okay."),
    ("[no speech]", ""),
    ("multi\n line", "multi line"),
])
def test_clean_transcript(raw, expected):
    assert clean_transcript(raw) == expected

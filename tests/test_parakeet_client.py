import threading

import numpy as np
import pytest

from voice_agent.audio.wav import encode_wav
from voice_agent.config import Config
from voice_agent.stt import create_client
from voice_agent.stt.ollama import OllamaTranscriptionClient
from voice_agent.stt.parakeet import ModelLoadError, ParakeetTranscriptionClient


class FakeModel:
    def __init__(self, replies=None):
        self.calls = []
        self.replies = list(replies or [])

    def recognize(self, samples, sample_rate):
        self.calls.append((samples.size, sample_rate, samples.dtype))
        return self.replies.pop(0) if self.replies else ""


def speech(seconds, sr=16000):
    t = np.arange(int(seconds * sr)) / sr
    return encode_wav(0.3 * np.sin(2 * np.pi * 220 * t), sr)


def make(model, **kw):
    loads = []

    def loader(name, quant, cache, threads):
        loads.append((name, quant, threads))
        return model
    return ParakeetTranscriptionClient(loader=loader, **kw), loads


def test_transcribe_single_chunk():
    model = FakeModel(["Hello  world."])
    client, loads = make(model)
    assert client.transcribe(speech(3)) == "Hello world."
    assert model.calls == [(48000, 16000, np.float32)]
    assert loads == [("nemo-parakeet-tdt-0.6b-v2", "int8", 0)]


def test_model_loaded_once_and_lazily():
    model = FakeModel(["a", "b"])
    client, loads = make(model)
    assert not client.is_loaded and loads == []
    client.transcribe(speech(1))
    client.transcribe(speech(1))
    assert len(loads) == 1


def test_concurrent_load_is_single():
    model = FakeModel()
    client, loads = make(model)
    threads = [threading.Thread(target=client.warm_up) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(loads) == 1


def test_long_audio_chunked():
    model = FakeModel(["One.", "Two."])
    client, _ = make(model, chunk_seconds=30)
    assert client.transcribe(speech(50)) == "One. Two."
    assert len(model.calls) == 2


def test_resamples_to_16k():
    model = FakeModel(["x"])
    client, _ = make(model)
    client.transcribe(speech(1, sr=48000))
    assert model.calls[0][:2] == (16000, 16000)


def test_silence_not_sent():
    model = FakeModel(["hallucination"])
    client, _ = make(model)
    assert client.transcribe(encode_wav(np.zeros(16000), 16000)) == ""
    assert model.calls == []


def test_load_failure_reported():
    def loader(*a):
        raise OSError("network down")
    client = ParakeetTranscriptionClient(loader=loader)
    status = client.health_check()
    assert not status.ok and "download" in status.message
    with pytest.raises(ModelLoadError):
        client.transcribe(speech(1))


def test_health_check_warms_up():
    model = FakeModel()
    client, _ = make(model)
    status = client.health_check()
    assert status.ok and len(model.calls) == 1


def test_factory():
    assert isinstance(create_client(Config()), ParakeetTranscriptionClient)
    assert isinstance(create_client(Config(stt_engine="ollama")), OllamaTranscriptionClient)
    c = create_client(Config(parakeet_quantization="", cpu_threads=2))
    assert c.quantization is None and c.cpu_threads == 2

import numpy as np

from voice_agent.audio.recorder import AudioRecorder
from voice_agent.audio.wav import decode_wav, encode_wav, resample, rms_level, split_chunks


def test_wav_roundtrip():
    sr = 16000
    t = np.arange(sr) / sr
    tone = 0.5 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    data = encode_wav(tone, sr)
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    out, rate = decode_wav(data)
    assert rate == sr
    assert out.size == sr
    assert np.max(np.abs(out - tone)) < 1e-3


def test_resample_length():
    x = np.zeros(48000, dtype=np.float32)
    assert resample(x, 48000, 16000).size == 16000
    assert resample(x, 16000, 16000).size == 48000


def test_rms_level():
    assert rms_level(np.zeros(100)) == 0.0
    assert abs(rms_level(np.ones(100, dtype=np.float32) * 0.5) - 0.5) < 1e-6


def test_split_short_audio_is_single_chunk():
    x = np.ones(16000, dtype=np.float32)
    chunks = split_chunks(x, 16000, 20)
    assert len(chunks) == 1 and chunks[0].size == 16000


def test_split_prefers_silence():
    sr = 1000
    x = np.ones(25 * sr, dtype=np.float32) * 0.5
    x[int(9.0 * sr):int(9.2 * sr)] = 0.0  # pause just before the 10 s limit
    chunks = split_chunks(x, sr, 10)
    assert sum(c.size for c in chunks) == x.size
    assert all(c.size <= 10 * sr for c in chunks)
    assert 9.0 * sr <= chunks[0].size <= 9.2 * sr


def test_split_empty():
    assert split_chunks(np.zeros(0), 16000, 20) == []


class FakeStream:
    def __init__(self, samplerate, channels, dtype, callback):
        if samplerate == 16000:
            raise RuntimeError("unsupported rate")
        self.rate = samplerate
        self.callback = callback

    def start(self):
        block = np.full((self.rate, 1), 0.25, dtype=np.float32)  # 1 s of audio
        self.callback(block, len(block), None, None)

    def stop(self):
        pass

    def close(self):
        pass


class FakeSD:
    InputStream = FakeStream

    @staticmethod
    def query_devices(kind):
        return {"default_samplerate": 48000.0}


def test_recorder_falls_back_and_resamples():
    rec = AudioRecorder(sd_module=FakeSD)
    rec.start()
    assert rec.is_recording
    assert rec.level > 0
    data = rec.stop()
    audio, rate = decode_wav(data)
    assert rate == 16000
    assert audio.size == 16000
    assert not rec.is_recording


def test_recorder_discards_short_clip():
    rec = AudioRecorder(sd_module=FakeSD, min_duration=2.0)
    rec.start()
    assert rec.stop() is None


def _tone(freq, seconds, sr, amp=0.5):
    t = np.arange(int(seconds * sr)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_resample_removes_out_of_band_tone():
    # A 12 kHz tone cannot exist at 16 kHz; linear interpolation would alias it to 4 kHz.
    out = resample(_tone(12000, 1.0, 48000), 48000, 16000)
    assert rms_level(out) < 0.01


def test_resample_preserves_in_band_tone():
    src = _tone(1000, 1.0, 48000)
    out = resample(src, 48000, 16000)
    expected = _tone(1000, 1.0, 16000)
    assert np.max(np.abs(out[100:-100] - expected[100:-100])) < 0.01


def test_trim_silence_keeps_padding():
    from voice_agent.audio.wav import trim_silence
    sr = 16000
    x = np.concatenate([np.zeros(sr), _tone(300, 1.0, sr), np.zeros(2 * sr)])
    out = trim_silence(x, sr, pad_seconds=0.2)
    assert abs(out.size / sr - 1.4) < 0.05


def test_trim_silence_all_silent():
    from voice_agent.audio.wav import trim_silence
    assert trim_silence(np.zeros(16000, dtype=np.float32), 16000).size == 0


def test_normalize_boosts_quiet_without_clipping():
    from voice_agent.audio.wav import normalize
    quiet = _tone(300, 0.5, 16000, amp=0.05)
    out = normalize(quiet)
    assert abs(np.max(np.abs(out)) - 0.4) < 0.01  # capped by max_gain=8
    loud = _tone(300, 0.5, 16000, amp=0.95)
    assert np.array_equal(normalize(loud), loud)


def test_recorder_discards_silence():
    class SilentStream(FakeStream):
        def start(self):
            self.callback(np.zeros((self.rate, 1), dtype=np.float32), self.rate, None, None)

    class SilentSD(FakeSD):
        InputStream = SilentStream

    rec = AudioRecorder(sd_module=SilentSD)
    rec.start()
    assert rec.stop() is None

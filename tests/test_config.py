import json

from voice_agent.config import Config, load_config, save_config


def test_defaults():
    cfg = Config()
    assert cfg.hotkey == "ctrl+win"
    assert cfg.hotkey_mode == "hold"
    assert cfg.model == "gemma4:e2b"
    assert cfg.ollama_url == "http://localhost:11434"


def test_missing_file_creates_defaults(tmp_path):
    path = tmp_path / "sub" / "config.json"
    cfg = load_config(path)
    assert cfg == Config()
    assert path.exists()


def test_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config(model="gemma4:e4b", chunk_seconds=10)
    save_config(cfg, path)
    assert load_config(path) == cfg


def test_unknown_and_invalid_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"bogus": 1, "chunk_seconds": "x", "num_ctx": 4096,
                                "hotkey_mode": "weird", "restore_clipboard": False}))
    cfg = load_config(path)
    assert cfg.chunk_seconds == Config().chunk_seconds
    assert cfg.num_ctx == 4096
    assert cfg.hotkey_mode == "hold"
    assert cfg.restore_clipboard is False


def test_corrupt_file_falls_back(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json")
    assert load_config(path) == Config()

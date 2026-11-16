# Implementation Stories

Each story is tracked as a GitHub issue. Acceptance criteria are listed per story.

## S1 — Select and integrate the local STT model (Ollama `gemma4:e2b`, superseded by S10)
As a user with a modest PC, I want dictation transcribed by a lightweight open-weight model
running in my local Ollama, so that my voice never leaves my machine.
- Model choice documented (`gemma4:e2b`, ~2B effective params, Q4_K_M, native audio input, English-first use).
- `OllamaTranscriptionClient` implements `TranscriptionClient`: sends 16 kHz mono 16-bit WAV (base64) to
  `POST /api/chat`, audio placed before the text instruction, `num_ctx` 8192, `temperature` 0.
- Long recordings are split into chunks (default 20 s) and the texts are joined.
- Clear error when Ollama is unreachable or the model is not pulled.
- Model, URL, prompt and chunk length configurable. Unit tests with a mocked HTTP layer.

## S2 — Configuration
- Settings stored as JSON in `%APPDATA%\VoiceAgent\config.json` (XDG fallback on other OSes).
- Defaults: hotkey `ctrl+win`, mode `hold`, Ollama `http://localhost:11434`, model `gemma4:e2b`.
- Unknown keys ignored, missing keys defaulted, corrupt file falls back to defaults. Unit tests.

## S3 — Audio capture from the default microphone
- Records from the system default input device via `sounddevice` at 16 kHz mono.
- `start()` / `stop()` return WAV bytes; very short clips (< 0.3 s) are discarded.
- Exposes the live input level for the overlay. Pure helpers (WAV encode, chunking) unit tested.

## S4 — Global hotkey (Ctrl + Win)
- Holding **Ctrl+Win** starts dictation, releasing either key stops it (`hold` mode);
  optional `toggle` mode (press once to start, again to stop).
- Combination parser supports `ctrl`, `win`, `alt`, `shift` and letters.
- Suppresses the Start menu popping up after Win is released.
- State machine is independent of pynput and unit tested.

## S5 — Text injection into the focused app
- Places the transcript on the clipboard, sends Ctrl+V to the focused window,
  then restores the previous clipboard text.
- Empty transcripts are not pasted.

## S6 — Orchestration and overlay states
- Controller wires hotkey → recorder → STT (worker thread) → injector.
- Overlay pill shows idle / listening (live mic level) / processing; errors shown via tray notification.
- UI never blocks while transcribing.

## S7 — System tray
- Tray icon with status, "Check Ollama", "Open config folder", and "Quit".
- Startup health check warns if Ollama is not running or the model is missing.

## S8 — Packaging, docs and CI
- PyInstaller spec and Inno Setup script for a Windows build.
- README: Ollama setup (`ollama pull gemma4:e2b`), usage, configuration, troubleshooting.
- GitHub Actions runs the unit tests on Windows and Linux.

## Round 2: faster, more accurate English speech recognition

`gemma4:e2b` through Ollama turned out to be slow and inaccurate for dictation. Ollama has
no real audio API, and an LLM decoding token by token is the wrong tool for speech
recognition. These stories replace it with a dedicated speech model.

## S9: Cleaner microphone audio (#10)
- Band-limited FFT resampling (48 kHz → 16 kHz) instead of linear interpolation.
- 250 ms recording tail after the hotkey is released, so the last word isn't clipped.
- Leading and trailing silence trimmed. Quiet microphones normalised without clipping.

## S10: NVIDIA Parakeet TDT 0.6B v2 as the default engine (#11)
- English-only, open weights (CC-BY-4.0), int8 ONNX (about 630 MB), run in-process with ONNX Runtime via `onnx-asr`.
- Downloaded once to `%LOCALAPPDATA%\VoiceAgent\models`, then fully offline.
- `stt_engine` = `parakeet` (default) or `ollama` (optional fallback).

## S11: Faster end-to-end latency and paste (#12)
- Model preloaded and warmed up at startup, with tray status.
- Modifier-release wait capped at 500 ms. Still-held modifiers are released synthetically before Ctrl+V.
- Per-dictation timing logs (no transcript text).

## S12: README and packaging for Parakeet (#13)
- README documents the model choice, measurements, setup, configuration and fallback.
- PyInstaller spec bundles ONNX Runtime and the `onnx-asr` data files.

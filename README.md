# Voice Agent

Voice-to-text desktop agent for Windows, similar in spirit to Wispr Flow: a minimal floating
overlay hovers center-screen and is activated by click or a push-to-talk hotkey. Recorded
audio is later sent to a cloud STT/LLM API for transcription.

## Stack

- Python 3.11+
- PySide6 (UI, tray)
- pynput (global hotkey / push-to-talk, text injection)
- sounddevice + numpy + soundfile (audio capture)
- keyring (API key storage)
- PyInstaller (packaging)

See the dev plan for full rationale and architecture.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```
python -m voice_agent.main
```

## Test

```
pytest
```

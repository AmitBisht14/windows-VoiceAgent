# Voice Agent

Private, offline voice dictation for Windows, in the spirit of Wispr Flow.
Hold **Ctrl + Win**, speak, and let go. Your words are transcribed by an open-weight
model running in your **local Ollama** and typed into whatever app has focus.
No audio leaves your computer.

## How it works

```
Ctrl+Win held ─► record default mic (16 kHz mono) ─► Ctrl+Win released
     ─► WAV sent to local Ollama (gemma4:e2b) ─► text pasted into the focused app
```

A small pill at the bottom of the screen shows the state:
grey dot = idle, red bars = listening, blue spinner = transcribing.
You can also left-click the pill to start or stop. Right-click it to quit.

## Speech-to-text model: `gemma4:e2b`

| Why | Details |
|---|---|
| Lightweight | Gemma 4 "E2B" has about 2B effective parameters, ships as Q4_K_M, and runs on CPU-only or low-VRAM PCs (8 GB RAM is workable, 16 GB is comfortable). |
| Audio-native | It is the smallest model in the Ollama library with a built-in audio encoder (about 300M params). No separate Whisper server is needed. |
| Good English | Accurate English transcription with punctuation and capitalization, guided by the prompt. |
| Open weights | Google's Gemma 4 licence, served entirely by your own Ollama. |

If you have more RAM or a GPU, `gemma4:e4b` is noticeably more accurate. Set `"model": "gemma4:e4b"` in the config.

> Ollama does not yet have a dedicated audio API field (ollama/ollama#11798). The app
> sends the recording as a base64 16 kHz mono WAV in the message's `images` list, which
> Ollama routes to the model's audio encoder. Recordings longer than 20 s are split
> at natural pauses and transcribed piece by piece. If a future Ollama version changes this,
> set `"ollama_api": "openai"` to use `/v1/chat/completions` with an `input_audio` part instead.

## Setup

1. Install [Ollama for Windows](https://ollama.com/download) and make sure it is running (tray icon).
2. Pull the model (one-time download of a few GB):
   ```
   ollama pull gemma4:e2b
   ```
3. Install Python 3.11+ and the app:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Run it:
   ```
   python -m voice_agent.main
   ```
   The tray icon reports "Ollama ready with gemma4:e2b" when everything is set up.

## Usage

- **Hold Ctrl + Win**, speak, then release. The text appears at your cursor.
- Pressing any other key while holding the combo (for example Ctrl+Win+→ to switch desktops) cancels the dictation.
- The first dictation after starting can take longer while Ollama loads the model.
  The model then stays loaded for 10 minutes (`keep_alive`).

## Configuration

Settings live in `%APPDATA%\VoiceAgent\config.json`, which is created on first run.
Open it from the tray menu with **Open config folder**, then restart the app after editing.

| Key | Default | Meaning |
|---|---|---|
| `hotkey` | `ctrl+win` | Key combo (`ctrl`, `win`, `alt`, `shift`, letters, `f1`–`f12`). |
| `hotkey_mode` | `hold` | `hold` = push-to-talk, `toggle` = press once to start and again to stop. |
| `ollama_url` | `http://localhost:11434` | Your Ollama server. |
| `model` | `gemma4:e2b` | Any audio-capable Ollama model. |
| `ollama_api` | `native` | `native` (`/api/chat`) or `openai` (`/v1/chat/completions`). |
| `prompt` | *(transcribe verbatim, English)* | Instruction sent with the audio. |
| `chunk_seconds` | `20` | Maximum audio length per request. |
| `num_ctx` | `8192` | Context window passed to Ollama. |
| `keep_alive` | `10m` | How long Ollama keeps the model in memory. |
| `max_duration` | `300` | Maximum recording length in seconds. |
| `restore_clipboard` | `true` | Put your previous clipboard text back after pasting. |
| `append_space` | `true` | Add a trailing space after each dictation. |

Logs are written to `%APPDATA%\VoiceAgent\voice_agent.log`. Transcript text is never logged.

## Troubleshooting

- **"Cannot reach Ollama"**: start Ollama, or check `ollama_url`.
- **"Model 'gemma4:e2b' is not installed"**: run `ollama pull gemma4:e2b`.
- **Nothing is typed into an admin app**: Windows blocks input from normal apps into
  elevated windows. Run Voice Agent as administrator too.
- **Wrong microphone**: the app uses the Windows default input device
  (Settings → System → Sound → Input).
- **Slow transcription**: keep dictations short, close other heavy apps, or use a GPU.

## Development

```
pip install -r requirements.txt
pytest
```

Project layout:

```
voice_agent/
  audio/      recorder.py (default mic capture), wav.py (encode/resample/chunk)
  hotkey/     state.py (pure hold/toggle state machine), listener.py (pynput hook)
  stt/        ollama.py (gemma4:e2b client), base.py, mock.py
  inject/     text_injector.py (clipboard + Ctrl+V)
  ui/         overlay.py (status pill), tray.py (tray menu)
  controller.py  wiring and threading
  config.py      JSON settings
```

Implementation stories are in [docs/STORIES.md](docs/STORIES.md).

## Packaging (Windows)

```
pyinstaller packaging/voice_agent.spec      # -> dist/VoiceAgent/VoiceAgent.exe
iscc packaging\installer.iss                # optional installer (Inno Setup 6)
```

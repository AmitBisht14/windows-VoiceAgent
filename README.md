# Voice Agent

Private, offline voice dictation for Windows, in the spirit of Wispr Flow.
Hold **Ctrl + Win**, speak, and let go. Your words are transcribed on your own PC by
**NVIDIA Parakeet TDT 0.6B v2**, a small, fast, English speech-recognition model,
and typed into whatever app has focus. No audio ever leaves your computer.

## How it works

```
Ctrl+Win held ─► record default mic ─► Ctrl+Win released (+250 ms tail)
   ─► clean audio (16 kHz, trim silence, normalise)
   ─► Parakeet TDT 0.6B v2 on ONNX Runtime (CPU, in-process)
   ─► text pasted into the focused app
```

A small pill at the bottom of the screen shows the state:
grey dot = idle, red bars = listening (they follow your voice), blue spinner = transcribing.
You can also left-click the pill to start or stop. Right-click it to quit.

## Speech model: NVIDIA Parakeet TDT 0.6B v2

| | **Parakeet TDT 0.6B v2 (default)** | gemma4:e2b via Ollama (previous) |
|---|---|---|
| Type | Dedicated speech recognizer (FastConformer + TDT decoder) | General LLM with an audio encoder |
| Language | English only, which is all we need | Multilingual |
| Download | **about 630 MB** (int8 ONNX) | about 5–8 GB |
| RAM while running | about 1–1.5 GB | several GB |
| Speed (4-core CPU, no GPU, measured) | **10 s of speech → about 0.8 s** | many seconds |
| Accuracy | About 6% average WER on the Hugging Face Open ASR leaderboard, ahead of Whisper large-v3. Punctuation and capitalization included. | Weak for dictation: missed and looped words |
| Needs a server | No, it runs inside the app | Yes, Ollama |
| Licence | CC-BY-4.0 (open weights) | Gemma licence |

Why not Ollama? Ollama runs LLMs. It has no real speech-to-text API and cannot load
dedicated speech models like Parakeet or Whisper, so the app runs Parakeet itself with
[ONNX Runtime](https://onnxruntime.ai) through the [`onnx-asr`](https://github.com/istupakov/onnx-asr)
package. The Ollama engine is still available as an option (see below).

Measured during development on a 4-core cloud CPU with the int8 model:

| Clip | Transcription time | Result |
|---|---|---|
| 9.7 s read speech | 0.79 s | "He hoped there would be stew for dinner, turnips and carrots and bruised potatoes and fat mutton pieces to be ladled out in thick, peppered, flour fattened sauce," |
| 11.9 s speech | 1.00 s | "I have a dream that one day this nation will rise up and live out the true meaning of its creed." |
| Model load at startup | 3–4 s (after the first download) | Loaded in the background while the app starts |

## Setup

1. Install **Python 3.11 or newer** (64-bit) from python.org.
2. Get the code and install the dependencies:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Run it:
   ```
   python -m voice_agent.main
   ```
   On the **first run** the speech model (about 630 MB) is downloaded from Hugging Face into
   `%LOCALAPPDATA%\VoiceAgent\models`. The tray menu shows "Loading speech model…" until
   it says "Speech model ready". After that the app works **fully offline** and never
   contacts the network again. An interrupted download resumes on the next start.

Ollama is **not** needed for the default setup.

## Usage

- **Hold Ctrl + Win**, speak, then release. The text appears at your cursor.
- Pressing any other key while holding the combo (for example Ctrl+Win+→ to switch desktops) cancels the dictation.
- Recording continues for a quarter of a second after release, so your last word isn't cut off.
- Your clipboard is restored after the text is pasted.

## Configuration

Settings live in `%APPDATA%\VoiceAgent\config.json`, which is created on first run.
Open it from the tray menu with **Open config folder**, then restart the app after editing.

| Key | Default | Meaning |
|---|---|---|
| `hotkey` | `ctrl+win` | Key combo (`ctrl`, `win`, `alt`, `shift`, letters, `f1`–`f12`). |
| `hotkey_mode` | `hold` | `hold` = push-to-talk, `toggle` = press once to start and again to stop. |
| `stt_engine` | `parakeet` | `parakeet` (local ONNX) or `ollama`. |
| `parakeet_model` | `nemo-parakeet-tdt-0.6b-v2` | Any English model `onnx-asr` supports. |
| `parakeet_quantization` | `int8` | `int8` (fast, small) or `""` for full precision (about 2.4 GB, slightly more accurate). |
| `parakeet_chunk_seconds` | `30` | Long recordings are split at pauses into pieces of this length. |
| `cpu_threads` | `0` | CPU threads for the model. `0` = automatic. |
| `tail_ms` | `250` | Extra recording time after you release the hotkey. |
| `max_duration` | `300` | Maximum recording length in seconds. |
| `restore_clipboard` | `true` | Put your previous clipboard text back after pasting. |
| `append_space` | `true` | Add a trailing space after each dictation. |
| `ollama_url`, `ollama_model`, `ollama_api`, `prompt`, `chunk_seconds`, `num_ctx`, `keep_alive` | | Only used when `stt_engine` is `ollama`. |

Logs are written to `%APPDATA%\VoiceAgent\voice_agent.log`, including per-dictation timings
such as `audio 4.2s, speech-to-text 0.41s, paste 0.02s`. Transcript text is never logged.

### Optional: use Ollama instead

If you prefer an Ollama model with audio input:

```
ollama pull gemma4:e2b
```

Then set `"stt_engine": "ollama"` (and optionally `"ollama_model"`) in `config.json`.
This is slower and less accurate than Parakeet on most PCs.

## Troubleshooting

- **"Could not load speech model … needs internet access"**: the first run must download
  the model. Check your connection or proxy and restart. Later runs are offline.
- **"Speech engine not installed"**: run `pip install "onnx-asr[cpu,hub]"`.
- **Nothing is typed into an admin app**: Windows blocks input from normal apps into
  elevated windows. Run Voice Agent as administrator too.
- **Wrong microphone**: the app uses the Windows default input device
  (Settings → System → Sound → Input).
- **Words missed**: speak at a normal distance from the mic and check the input level in
  Windows sound settings. Very quiet input is boosted automatically, up to 8×.

## Development

```
pip install -r requirements.txt
pytest
```

The tests use fakes for the microphone, keyboard and speech model, so they don't need the model download.

Project layout:

```
voice_agent/
  audio/      recorder.py (default mic capture), wav.py (resample/trim/normalise/chunk)
  hotkey/     state.py (pure hold/toggle state machine), listener.py (pynput hook)
  stt/        parakeet.py (default engine), ollama.py (optional), base.py, mock.py
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

The speech model is not bundled into the installer. It is downloaded on first launch.

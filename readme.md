# Embodied Rocky AI

## Basic stuff

- You can type to Rocky or talk to Rocky through your microphone.
- Local `faster-whisper` transcription turns microphone audio into text.
- Claude will generate a reply in Rocky's voice and personality, all tunable in `rocky_system.txt`.
- Cartesia turns the reply into audio with a higher-quality conversational voice.
- The app can still fall back to built-in macOS speech if you want a free local backup.

This is the simplest version of the eventual full puppet pipeline:

`human input -> character brain -> voice output`

## Repo Layout

- `src/rocky_mvp.py` - terminal app
- `prompts/rocky_system.txt` - Rocky system prompt
- `.env.example` - environment variables
- `requirements.txt` - Python dependencies

## Setup

1. Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy the example env file:

```bash
cp .env.example .env
```

4. Fill in your keys in `.env`:

- `ANTHROPIC_API_KEY`
- `CARTESIA_API_KEY`
- `CARTESIA_VOICE_ID`

## Run

```bash
python -m src.rocky_mvp
```

Then type to Rocky. Use `quit` or `exit` to stop.

To use microphone input, set:

```env
INPUT_MODE=voice
```

In voice mode, press Enter once to start recording and press Enter again to stop. The app will transcribe your speech, send it to Rocky, and speak the reply back.

To use automatic speech-end detection, set:

```env
INPUT_MODE=voice_vad
```

In `voice_vad` mode, Rocky listens continuously, starts recording when speech is detected, and stops automatically after trailing silence. The current manual `voice` mode remains available as a fallback.

## Notes

- The prompt is deliberately stored in a separate text file so you can iterate on Rocky's voice quickly.
- Conversation history is kept in memory for the current session.
- Voice input uses local `faster-whisper`, so there is no transcription API cost (ur welcome).
- The first transcription run may download the selected Whisper model to your machine.
- `voice_vad` uses WebRTC VAD, which expects 16-bit mono PCM audio at 8000, 16000, or 32000 Hz and frame sizes of 10, 20, or 30 ms.
- `TTS_BACKEND=cartesia` is the default.
- If Cartesia is unavailable, you can switch to `TTS_BACKEND=macos_say`. (Note: TTS through this method sounds completely devoid of life)
- You can tune `WHISPER_MODEL_SIZE`, `WHISPER_COMPUTE_TYPE`, `CARTESIA_MODEL_ID`, `CARTESIA_VOICE_ID`, `CARTESIA_SPEED`, the manual microphone settings, and the VAD thresholds in `.env`.

## Character Tuning

Treat `prompts/rocky_system.txt` like code.

When Rocky says something that feels off:
- adjust the speech rules
- add or remove examples
- tighten the constraints
- rerun and compare

The fastest path to a believable character is lots of short prompt iterations!!!

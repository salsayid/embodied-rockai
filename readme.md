# Embodied Rocky AI

Software-first MVP for a physical Rocky animatronic inspired by *Project Hail Mary*.

The goal of this repo is to get the character and conversation loop feeling right before any hardware work starts.

## What This MVP Does

- You type to Rocky in the terminal.
- Anthropic generates a reply in Rocky's voice and personality.
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

## Notes

- The prompt is deliberately stored in a separate text file so you can iterate on Rocky's voice quickly.
- Conversation history is kept in memory for the current session.
- `TTS_BACKEND=cartesia` is the default.
- If Cartesia is unavailable, you can switch to `TTS_BACKEND=macos_say`.
- You can tune `CARTESIA_MODEL_ID`, `CARTESIA_VOICE_ID`, and `CARTESIA_SPEED` in `.env`.

## Next Steps

- Add microphone input with Whisper
- Add VAD for fast turn detection
- Stream Claude text as it is generated
- Replace one-shot TTS playback with streaming audio output
- Drive jaw movement from audio amplitude
- Send mouth openness values over serial to an Arduino

## Character Tuning

Treat `prompts/rocky_system.txt` like code.

When Rocky says something that feels off:

- adjust the speech rules
- add or remove examples
- tighten the constraints
- rerun and compare

The fastest path to a believable character is lots of short prompt iterations.

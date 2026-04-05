from __future__ import annotations

import io
import os
import platform
import subprocess
import tempfile
import threading
import wave
from pathlib import Path
from typing import Dict, List

from anthropic import Anthropic
from dotenv import load_dotenv
from faster_whisper import WhisperModel
import requests
import sounddevice as sd


ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "prompts" / "rocky_system.txt"
WHISPER_MODEL: WhisperModel | None = None


def load_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_messages(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [{"role": item["role"], "content": item["content"]} for item in history]


def generate_reply(client: Anthropic, system_prompt: str, history: List[Dict[str, str]]) -> str:
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    max_tokens = int(os.getenv("MAX_TOKENS", "220"))
    temperature = float(os.getenv("TEMPERATURE", "0.6"))

    response = client.messages.create(
        model=model,
        system=system_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=build_messages(history),
    )

    text_parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    return "".join(text_parts).strip()


def get_whisper_model() -> WhisperModel:
    global WHISPER_MODEL

    if WHISPER_MODEL is not None:
        return WHISPER_MODEL

    model_size = os.getenv("WHISPER_MODEL_SIZE", "base").strip() or "base"
    model_device = os.getenv("WHISPER_DEVICE", "auto").strip() or "auto"
    compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip() or "int8"

    print(f"Loading faster-whisper model `{model_size}` on `{model_device}`...")
    WHISPER_MODEL = WhisperModel(model_size, device=model_device, compute_type=compute_type)
    return WHISPER_MODEL


def transcribe_audio(audio_bytes: bytes) -> str:
    model = get_whisper_model()
    language = os.getenv("WHISPER_LANGUAGE", "en").strip() or "en"
    beam_size = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
    vad_filter = os.getenv("WHISPER_VAD_FILTER", "true").strip().lower() in {"1", "true", "yes", "on"}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    try:
        segments, info = model.transcribe(
            str(tmp_path),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
        )
        segment_list = list(segments)
    except Exception as exc:
        raise RuntimeError(f"faster-whisper transcription failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    text = " ".join(segment.text.strip() for segment in segment_list if segment.text.strip()).strip()
    if not text:
        raise RuntimeError("faster-whisper returned no text.")

    print(f"Detected language: {info.language} ({info.language_probability:.2f})")
    return text


def explain_error(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()

    if "invalid x-api-key" in lowered or "authentication_error" in lowered:
        return (
            "Anthropic rejected ANTHROPIC_API_KEY. Check that `.env` contains a real Anthropic key, "
            "not a placeholder, old key, or ElevenLabs key."
        )

    if "faster-whisper transcription failed" in lowered:
        return "Local faster-whisper transcription failed. Check your microphone audio, model settings, or first-run model download."

    if "microphone capture failed" in lowered:
        return "Microphone capture failed. Check macOS microphone permission and your selected input device."

    if "say" in lowered and "no such file or directory" in lowered:
        return "macOS `say` was not found. This free local speech path currently expects macOS."

    if "cartesia" in lowered and "401" in lowered:
        return "Cartesia rejected CARTESIA_API_KEY. Check that your `.env` contains a real Cartesia API key."

    if "cartesia" in lowered and "404" in lowered:
        return "Cartesia could not find that voice or model. Check CARTESIA_VOICE_ID and CARTESIA_MODEL_ID in `.env`."

    if "cartesia" in lowered and "402" in lowered:
        return "Cartesia returned 402 Payment Required. The API key likely works, but the account or plan cannot generate audio right now."

    return message


def prompt_for_user_text() -> str:
    input_mode = os.getenv("INPUT_MODE", "text").strip().lower() or "text"

    if input_mode == "voice":
        return prompt_for_voice_input()

    return input("\nYou: ").strip()


def prompt_for_voice_input() -> str:
    sample_rate = int(os.getenv("MIC_SAMPLE_RATE", "16000"))
    channels = int(os.getenv("MIC_CHANNELS", "1"))
    blocksize = int(os.getenv("MIC_BLOCKSIZE", "1024"))
    max_seconds = float(os.getenv("MIC_MAX_SECONDS", "20"))

    input("\nPress Enter to start recording.")
    print("Recording... press Enter to stop.")

    stop_event = threading.Event()

    def wait_for_stop() -> None:
        input()
        stop_event.set()

    waiter = threading.Thread(target=wait_for_stop, daemon=True)
    waiter.start()

    frames: List[bytes] = []
    max_frames = max(1, int(sample_rate * max_seconds))
    collected_frames = 0

    try:
        with sd.RawInputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            blocksize=blocksize,
        ) as stream:
            while not stop_event.is_set() and collected_frames < max_frames:
                chunk, overflowed = stream.read(blocksize)
                if overflowed:
                    print("Microphone buffer overflowed; continuing with captured audio.")
                frames.append(bytes(chunk))
                collected_frames += blocksize
    except Exception as exc:
        raise RuntimeError(f"Microphone capture failed: {exc}") from exc

    stop_event.set()

    if not frames:
        raise RuntimeError("No audio was captured from the microphone.")

    if collected_frames >= max_frames:
        print(f"Reached max recording length of {max_seconds:.0f} seconds. Stopping automatically.")

    audio_bytes = wav_bytes_from_frames(frames, sample_rate=sample_rate, channels=channels, sample_width=2)
    transcript = transcribe_audio(audio_bytes)
    print(f"\nYou said: {transcript}")
    return transcript


def wav_bytes_from_frames(frames: List[bytes], sample_rate: int, channels: int, sample_width: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"".join(frames))
    return buffer.getvalue()


def speak_text_macos(text: str) -> None:
    system = platform.system()
    if system != "Darwin":
        raise RuntimeError(
            "Local free speech is currently configured for macOS only. Add another local TTS backend for this platform."
        )

    voice = os.getenv("MACOS_TTS_VOICE", "Samantha").strip() or "Samantha"
    rate = os.getenv("MACOS_TTS_RATE", "185").strip() or "185"
    subprocess.run(["say", "-v", voice, "-r", rate, text], check=True)


def synthesize_speech_cartesia(text: str) -> bytes:
    api_key = load_required_env("CARTESIA_API_KEY")
    version = os.getenv("CARTESIA_VERSION", "2026-03-01").strip() or "2026-03-01"
    model_id = os.getenv("CARTESIA_MODEL_ID", "sonic-3").strip() or "sonic-3"
    voice_id = load_required_env("CARTESIA_VOICE_ID")
    language = os.getenv("CARTESIA_LANGUAGE", "en").strip() or "en"
    speed = float(os.getenv("CARTESIA_SPEED", "1.0"))

    response = requests.post(
        "https://api.cartesia.ai/tts/bytes",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Cartesia-Version": version,
            "Content-Type": "application/json",
        },
        json={
            "model_id": model_id,
            "transcript": text,
            "voice": {
                "mode": "id",
                "id": voice_id,
            },
            "language": language,
            "output_format": {
                "container": "wav",
                "encoding": "pcm_f32le",
                "sample_rate": 44100,
            },
            "generation_config": {
                "speed": speed,
            },
        },
        timeout=90,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(f"Cartesia error: {exc}") from exc
    return response.content


def play_audio_bytes(audio_bytes: bytes, suffix: str = ".wav") -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    system = platform.system()
    if system == "Darwin":
        command = ["afplay", str(tmp_path)]
    elif system == "Linux":
        command = ["xdg-open", str(tmp_path)]
    elif system == "Windows":
        command = ["powershell", "-c", f'(New-Object Media.SoundPlayer "{tmp_path}").PlaySync();']
    else:
        print(f"Audio saved to {tmp_path}")
        return

    try:
        subprocess.run(command, check=True)
    finally:
        tmp_path.unlink(missing_ok=True)


def speak_text(text: str) -> None:
    backend = os.getenv("TTS_BACKEND", "cartesia").strip().lower() or "cartesia"

    if backend == "cartesia":
        audio = synthesize_speech_cartesia(text)
        play_audio_bytes(audio)
        return

    if backend in {"macos", "macos_say", "say"}:
        speak_text_macos(text)
        return

    raise RuntimeError(f"Unsupported TTS_BACKEND: {backend}")


def main() -> None:
    load_dotenv()

    anthropic_api_key = load_required_env("ANTHROPIC_API_KEY")
    system_prompt = load_prompt()
    client = Anthropic(api_key=anthropic_api_key)
    history: List[Dict[str, str]] = []

    print("Rocky terminal MVP")
    input_mode = os.getenv("INPUT_MODE", "text").strip().lower() or "text"
    if input_mode == "voice":
        print("Voice mode is on. Press Enter to start and stop each recording. Say 'quit' or 'exit' to stop.")
    else:
        print("Type to Rocky. Use 'quit' or 'exit' to stop.")

    while True:
        try:
            user_text = prompt_for_user_text()
        except Exception as exc:
            print(f"\nInput unavailable: {explain_error(exc)}")
            continue

        if not user_text:
            continue
        if user_text.lower() in {"quit", "exit"}:
            print("Ending session.")
            break

        history.append({"role": "user", "content": user_text})

        try:
            rocky_reply = generate_reply(client, system_prompt, history)
            history.append({"role": "assistant", "content": rocky_reply})

            print(f"\nRocky: {rocky_reply}")
        except Exception as exc:
            print(f"\nError: {explain_error(exc)}")
            continue

        try:
            speak_text(rocky_reply)
        except Exception as exc:
            print(f"\nAudio unavailable: {explain_error(exc)}")
            print("Rocky will keep responding in text while local speech is unavailable.")


if __name__ == "__main__":
    main()

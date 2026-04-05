from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import List, Dict

from anthropic import Anthropic
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "prompts" / "rocky_system.txt"


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


def explain_error(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()

    if "invalid x-api-key" in lowered or "authentication_error" in lowered:
        return (
            "Anthropic rejected ANTHROPIC_API_KEY. Check that `.env` contains a real Anthropic key, "
            "not a placeholder, old key, or ElevenLabs key."
        )

    if "say" in lowered and "no such file or directory" in lowered:
        return "macOS `say` was not found. This free local speech path currently expects macOS."

    return message


def speak_text(text: str) -> None:
    system = platform.system()
    if system != "Darwin":
        raise RuntimeError(
            "Local free speech is currently configured for macOS only. Add another local TTS backend for this platform."
        )

    voice = os.getenv("MACOS_TTS_VOICE", "Samantha").strip() or "Samantha"
    rate = os.getenv("MACOS_TTS_RATE", "185").strip() or "185"
    subprocess.run(["say", "-v", voice, "-r", rate, text], check=True)


def main() -> None:
    load_dotenv()

    anthropic_api_key = load_required_env("ANTHROPIC_API_KEY")
    system_prompt = load_prompt()
    client = Anthropic(api_key=anthropic_api_key)
    history: List[Dict[str, str]] = []

    print("Rocky terminal MVP")
    print("Type to Rocky. Use 'quit' or 'exit' to stop.")

    while True:
        user_text = input("\nYou: ").strip()
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

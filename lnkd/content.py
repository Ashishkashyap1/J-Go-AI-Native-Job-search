"""
content.py — offline post/message drafting via a local Ollama model.

No cloud calls. Requires Ollama running locally (`ollama serve`) with a model
pulled (`ollama pull qwen2.5:7b`). Host/model configurable in config.toml.
"""
from __future__ import annotations

import httpx

from . import config

POST_SYSTEM = (
    "You write LinkedIn posts. Rules: no hash&#45;tag spam (max 3), no emoji "
    "walls, no 'I'm humbled to announce'. Sound like a real practitioner. "
    "Keep it under 1300 characters. Output only the post text."
)

DM_SYSTEM = (
    "You write short, specific LinkedIn connection notes (under 280 chars). "
    "Reference the person's actual work. No flattery, no 'I'd love to pick "
    "your brain'. Output only the note."
)


def _generate(system: str, prompt: str) -> str:
    cfg = config.Settings.load()
    r = httpx.post(
        f"{cfg.ollama_host}/api/chat",
        json={
            "model": cfg.ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def draft_post(topic: str, tone: str = "practical") -> str:
    return _generate(POST_SYSTEM, f"Topic: {topic}\nTone: {tone}\nWrite the post.")


def draft_note(person_name: str, headline: str, why: str) -> str:
    return _generate(
        DM_SYSTEM,
        f"Person: {person_name} — {headline}\nWhy connect: {why}\nWrite the note.",
    )

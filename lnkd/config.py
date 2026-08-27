"""
config.py — paths, config file, and secret storage.

Secrets (LinkedIn session cookie, OAuth token) go into the OS keyring via the
`keyring` package, NEVER into a plaintext file. Non-secret settings live in a
small TOML config.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:
    import keyring
except Exception:  # keyring optional at import time; required for live use
    keyring = None

APP = "lnkd"
CONFIG_DIR = Path(os.environ.get("LNKD_HOME", Path.home() / ".config" / APP))
CONFIG_FILE = CONFIG_DIR / "config.toml"
DB_FILE = CONFIG_DIR / "state.db"


@dataclass
class Settings:
    timezone: str = "UTC"
    work_start: int = 8
    work_end: int = 22
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    # official API app (create at linkedin.com/developers) — client id is not secret
    oauth_client_id: str = ""
    oauth_redirect: str = "http://localhost:8765/callback"

    @classmethod
    def load(cls) -> "Settings":
        if CONFIG_FILE.exists():
            data = tomllib.loads(CONFIG_FILE.read_text())
            return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
        return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        lines = []
        for k, v in asdict(self).items():
            if isinstance(v, str):
                lines.append(f'{k} = "{v}"')
            else:
                lines.append(f"{k} = {v}")
        CONFIG_FILE.write_text("\n".join(lines) + "\n")


# ---- secret helpers ---------------------------------------------------------

def _require_keyring():
    if keyring is None:
        raise RuntimeError("keyring not installed. `pip install keyring`")


def set_secret(name: str, value: str) -> None:
    _require_keyring()
    keyring.set_password(APP, name, value)


def get_secret(name: str) -> str | None:
    _require_keyring()
    return keyring.get_password(APP, name)


def clear_secret(name: str) -> None:
    _require_keyring()
    try:
        keyring.delete_password(APP, name)
    except Exception:
        pass

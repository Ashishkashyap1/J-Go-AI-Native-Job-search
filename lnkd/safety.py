"""
safety.py — the load-bearing wall.

Every action that touches LinkedIn MUST pass through Guard.check() first.
If this module says stop, nothing else runs. That is the whole point:
the account survives only as long as this file is respected.

Design principles:
  * Caps live BELOW LinkedIn's own published limits, never at them.
  * Randomized, human-like pacing — no fixed intervals a detector can fingerprint.
  * A circuit breaker trips permanently for the session on the first sign of a
    challenge (CAPTCHA / checkpoint / 999 / rate-limit response).
  * Working-hours guard: no 3am robotic bursts.
  * Everything is persisted so caps survive process restarts (you can't dodge
    the weekly cap by killing and relaunching).
"""
from __future__ import annotations

import datetime as dt
import random
import time
from dataclasses import dataclass
from enum import Enum
from zoneinfo import ZoneInfo

from .store import Store


class Action(str, Enum):
    CONNECT = "connect"
    MESSAGE = "message"
    SEARCH = "search"
    VIEW = "view"
    POST = "post"          # official API — not rate-gated the same way, but logged


# Deliberately conservative. LinkedIn's soft limit is ~100 invites/week; we cap
# well under it. Tune DOWN, never up. These are per-rolling-window.
CAPS = {
    Action.CONNECT: {"per_day": 15, "per_week": 60,  "min_gap_s": 45},
    Action.MESSAGE: {"per_day": 20, "per_week": 120, "min_gap_s": 30},
    Action.SEARCH:  {"per_day": 80, "per_week": 400, "min_gap_s": 8},
    Action.VIEW:    {"per_day": 120,"per_week": 600, "min_gap_s": 5},
    Action.POST:    {"per_day": 5,  "per_week": 20,  "min_gap_s": 0},
}

# Substrings in a response body / status that mean "LinkedIn noticed you."
CHALLENGE_SIGNALS = (
    "checkpoint", "captcha", "challenge", "unusual activity",
    "verify it's you", "add-phone", "999", "please verify",
)


class CircuitOpen(Exception):
    """Raised when the breaker has tripped. Nothing should proceed."""


class CapReached(Exception):
    """Raised when a daily/weekly cap is hit. Try again later, not now."""


@dataclass
class Guard:
    store: Store
    tz: str = "UTC"
    work_start: int = 8          # 24h local; no actions outside these hours
    work_end: int = 22
    dry_run: bool = False
    _breaker_tripped: bool = False
    _breaker_reason: str = ""

    # ---- public API ---------------------------------------------------------

    def check(self, action: Action) -> None:
        """Gate an action. Raises if it must not happen right now."""
        if self._breaker_tripped:
            raise CircuitOpen(f"circuit open: {self._breaker_reason}")

        self._working_hours_guard()

        caps = CAPS[action]
        day = self.store.count_since(action.value, self._window_start("day"))
        week = self.store.count_since(action.value, self._window_start("week"))
        if day >= caps["per_day"]:
            raise CapReached(f"{action.value}: daily cap {caps['per_day']} reached")
        if week >= caps["per_week"]:
            raise CapReached(f"{action.value}: weekly cap {caps['per_week']} reached")

        self._min_gap_guard(action, caps["min_gap_s"])

    def human_pause(self, action: Action) -> None:
        """Sleep a human-ish amount AFTER a successful action."""
        base = CAPS[action]["min_gap_s"]
        # log-normal-ish jitter so gaps cluster low but occasionally run long,
        # like a real person who sometimes gets distracted.
        jitter = random.expovariate(1 / max(base, 3))
        delay = base + jitter + random.uniform(0, base * 0.5)
        if self.dry_run:
            delay = min(delay, 0.2)
        time.sleep(delay)

    def record(self, action: Action, target: str = "", ok: bool = True,
               note: str = "") -> None:
        """Persist that an action happened. Caps read from this."""
        self.store.log_action(action.value, target=target, ok=ok, note=note)

    def inspect_response(self, status: int, body: str) -> None:
        """
        Call after every LinkedIn HTTP response. Trips the breaker on any
        sign LinkedIn is challenging the session. Fail closed, not open.
        """
        low = (body or "").lower()
        if status in (429, 999) or any(s in low for s in CHALLENGE_SIGNALS):
            self.trip(f"challenge signal (HTTP {status})")

    def trip(self, reason: str) -> None:
        self._breaker_tripped = True
        self._breaker_reason = reason
        self.store.log_action("breaker", target="", ok=False, note=reason)

    @property
    def tripped(self) -> bool:
        return self._breaker_tripped

    # ---- internals ----------------------------------------------------------

    def _now(self) -> dt.datetime:
        return dt.datetime.now(ZoneInfo(self.tz))

    def _working_hours_guard(self) -> None:
        h = self._now().hour
        if not (self.work_start <= h < self.work_end):
            raise CapReached(
                f"outside working hours ({self.work_start}:00-{self.work_end}:00 {self.tz})"
            )

    def _window_start(self, kind: str) -> dt.datetime:
        now = self._now()
        if kind == "day":
            return now - dt.timedelta(days=1)
        return now - dt.timedelta(days=7)

    def _min_gap_guard(self, action: Action, min_gap_s: int) -> None:
        last = self.store.last_action_time(action.value)
        if last is None:
            return
        elapsed = (self._now() - last).total_seconds()
        if elapsed < min_gap_s:
            time.sleep(min_gap_s - elapsed if not self.dry_run else 0.05)

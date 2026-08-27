"""
session.py — authentication + the Voyager HTTP base client.

Strategy (the hybrid that keeps you alive longest):
  * LOGIN is done ONCE via a real Chromium window (Playwright). You type your
    password / solve any 2FA yourself, like a human. We then harvest the
    `li_at` and `JSESSIONID` cookies. This avoids the heavily-flagged pattern
    of programmatic username/password POSTs.
  * ACTIONS use those cookies against the Voyager API (the same private API
    LinkedIn's own web client calls), with the correct headers so requests
    look like the web app, not a script.

The cookie is a secret — it is stored in the OS keyring, never on disk.
"""
from __future__ import annotations

import json

import httpx

from . import config
from .safety import Guard

VOYAGER = "https://www.linkedin.com/voyager/api"
COOKIE_KEY = "li_session_cookies"   # keyring entry: JSON {li_at, JSESSIONID}


def harvest_cookies_interactive() -> dict:
    """
    Open a real browser, let the human log in, then pull the session cookies.
    Requires: `pip install playwright && playwright install chromium`.
    """
    from playwright.sync_api import sync_playwright  # imported lazily

    wanted = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto("https://www.linkedin.com/login")
        print(">> Log in in the browser window (solve any 2FA/CAPTCHA yourself).")
        print(">> When your feed has loaded, come back here and press Enter.")
        input()
        for c in ctx.cookies():
            if c["name"] in ("li_at", "JSESSIONID"):
                wanted[c["name"]] = c["value"]
        browser.close()

    if "li_at" not in wanted:
        raise RuntimeError("Did not find li_at cookie — login incomplete.")
    config.set_secret(COOKIE_KEY, json.dumps(wanted))
    return wanted


def load_cookies() -> dict:
    raw = config.get_secret(COOKIE_KEY)
    if not raw:
        raise RuntimeError("No session stored. Run `lnkd auth login` first.")
    return json.loads(raw)


class Voyager:
    """Thin client over the private Voyager API. Every response is fed to the
    Guard so the circuit breaker can trip on any challenge signal."""

    def __init__(self, guard: Guard):
        self.guard = guard
        cookies = load_cookies()
        jsession = cookies.get("JSESSIONID", "").strip('"')
        self.client = httpx.Client(
            base_url=VOYAGER,
            timeout=20,
            headers={
                "csrf-token": jsession,
                "x-restli-protocol-version": "2.0.0",
                "x-li-lang": "en_US",
                "user-agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "accept": "application/vnd.linkedin.normalized+json+2.1",
            },
            cookies={
                "li_at": cookies["li_at"],
                "JSESSIONID": cookies.get("JSESSIONID", ""),
            },
        )

    def get(self, path: str, **kw) -> httpx.Response:
        r = self.client.get(path, **kw)
        self.guard.inspect_response(r.status_code, r.text[:500])
        return r

    def post(self, path: str, **kw) -> httpx.Response:
        r = self.client.post(path, **kw)
        self.guard.inspect_response(r.status_code, r.text[:500])
        return r

    def close(self):
        self.client.close()

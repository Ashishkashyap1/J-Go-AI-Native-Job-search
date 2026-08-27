# lnkd — LinkedIn all-rounder CLI

A single CLI for posting, connecting, messaging, and searching on LinkedIn,
with a local (offline) model for content drafting.

## Read this first — the risk is real

This tool has **two halves**:

| Half | Commands | Status |
|------|----------|--------|
| **Safe** | `post text/image/draft` | Uses LinkedIn's *official* `w_member_social` API. Sanctioned. |
| **Gray** | `search`, `connect`, `message` | Uses the *private Voyager API*. **Violates LinkedIn's User Agreement.** Detection can restrict or ban your account. |

The gray half exists behind guard rails, not because it's safe, but because if
you're going to do it anyway, doing it *carefully* is the difference between
months of use and a ban in a week. **Your call, your account, your risk.**

## Design: the safety wall

`safety.py` gates **every** LinkedIn action:

- Daily/weekly caps set **below** LinkedIn's own limits (~100 invites/week).
- Randomized, human-like pacing (no fixed intervals to fingerprint).
- A **circuit breaker** that trips permanently for the session on the first
  challenge signal (CAPTCHA / checkpoint / HTTP 429 / 999).
- A **working-hours guard** — no 3am robotic bursts.
- Caps persist in SQLite, so killing and relaunching won't dodge them.

`--dry-run` is **ON by default** for every gray command. You must explicitly
`--no-dry-run` (and confirm) to send anything real.

## Setup

```bash
pip install -e .
playwright install chromium        # for auth login only

# local model for drafting
ollama pull qwen2.5:7b             # or set ollama_model in config.toml

# authenticate the gray half (browser login, you solve any 2FA)
lnkd auth login

# authenticate the safe half (register an app at linkedin.com/developers,
# put client_id in config.toml, then:)
lnkd auth oauth
```

## Usage

```bash
# safe
lnkd post draft "what I learned shipping a rate limiter" --tone practical
lnkd post image chart.png "Q3 numbers"

# gray — dry-run first (default), then arm
lnkd search "data annotation lead" --limit 10
lnkd connect "MLOps engineer" -n 8 --ai-note            # dry-run
lnkd connect "MLOps engineer" -n 8 --ai-note --no-dry-run   # armed, confirms

lnkd status        # caps used, breaker state, recent actions
```

## What is NOT here (and why)

- **Bulk messaging sequences** — the single most-detected behavior. Left out on
  purpose. Send few, specific, manual-quality messages.
- **Sales Navigator** — extra detection layer; out of scope for personal use.
- **Feed scraping / auto-engagement** — brittle Voyager endpoints, high risk,
  low value.

## Endpoint drift

Voyager paths change without notice. They're isolated in `voyager.py` and
`session.py` so a break is a one-file fix. If `search`/`connect` suddenly 400s,
that's the place to look — LinkedIn moved the goalposts, not a bug in your caps.

## Roadmap

- [ ] OAuth token exchange command (`auth token`) + refresh
- [ ] Post scheduler (cron-friendly `post schedule`)
- [ ] YAML campaign files + outbox queue
- [ ] Response tracking (who accepted / replied)
- [ ] Encrypted export/import of contacted-list

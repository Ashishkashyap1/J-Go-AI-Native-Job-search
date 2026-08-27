"""
cli.py — the command-line surface.

  lnkd auth login              # browser login -> harvest session cookies
  lnkd auth oauth              # authorize official posting app
  lnkd post text "..."         # official API (safe)
  lnkd post image img.png "..."# official API (safe)
  lnkd post draft "topic"      # local model drafts, you confirm, then post
  lnkd search "keywords"       # voyager (gray)
  lnkd connect "keywords" -n 10# voyager invites w/ optional AI note (gray)
  lnkd message <urn> "..."     # voyager DM (gray)
  lnkd status                  # caps used, breaker state, recent log

Global flags: --dry-run (default ON for gray actions until you opt out),
              --yes (skip confirms).
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from . import config, content, official
from .safety import Action, CAPS, CapReached, CircuitOpen, Guard
from .session import Voyager, harvest_cookies_interactive
from .store import Store
from .voyager import Gray, Person

app = typer.Typer(add_completion=False, help="LinkedIn all-rounder CLI.")
auth_app = typer.Typer(help="Authentication")
post_app = typer.Typer(help="Posting (official API — safe)")
app.add_typer(auth_app, name="auth")
app.add_typer(post_app, name="post")
con = Console()


def _guard(dry_run: bool) -> tuple[Guard, Store]:
    cfg = config.Settings.load()
    store = Store(config.DB_FILE)
    g = Guard(store=store, tz=cfg.timezone, work_start=cfg.work_start,
              work_end=cfg.work_end, dry_run=dry_run)
    return g, store


# ---- auth -------------------------------------------------------------------

@auth_app.command("login")
def auth_login():
    """Open a browser, log in yourself, harvest session cookies."""
    harvest_cookies_interactive()
    con.print("[green]Session stored in keyring.[/green]")


@auth_app.command("oauth")
def auth_oauth():
    """Print the OAuth URL for the official posting app."""
    cfg = config.Settings.load()
    if not cfg.oauth_client_id:
        con.print("[red]Set oauth_client_id in config first.[/red]")
        raise typer.Exit(1)
    url = (
        "https://www.linkedin.com/oauth/v2/authorization?response_type=code"
        f"&client_id={cfg.oauth_client_id}&redirect_uri={cfg.oauth_redirect}"
        "&scope=w_member_social%20openid%20profile"
    )
    con.print("Open this, authorize, paste the ?code=... into `lnkd auth token`:")
    con.print(url)


# ---- post (safe) ------------------------------------------------------------

@post_app.command("text")
def post_text(text: str, dry_run: bool = False):
    con.print(official.post_text(text, dry_run=dry_run))


@post_app.command("image")
def post_image(image: str, text: str, dry_run: bool = False):
    from pathlib import Path
    con.print(official.post_image(text, Path(image), dry_run=dry_run))


@post_app.command("draft")
def post_draft(topic: str, tone: str = "practical", yes: bool = False,
               dry_run: bool = False):
    """Local model drafts a post; you approve before it publishes."""
    draft = content.draft_post(topic, tone)
    con.rule("draft")
    con.print(draft)
    con.rule()
    if not yes and not typer.confirm("Publish this?"):
        raise typer.Exit()
    con.print(official.post_text(draft, dry_run=dry_run))


# ---- gray half --------------------------------------------------------------

@app.command()
def search(keywords: str, limit: int = 10, dry_run: bool = True):
    g, store = _guard(dry_run)
    voy = Voyager(g)
    try:
        people = Gray(voy, g, store).search_people(keywords, limit)
    finally:
        voy.close()
    t = Table("name", "headline", "urn")
    for p in people:
        t.add_row(p.name, p.headline[:40], p.urn[-12:])
    con.print(t)


@app.command()
def connect(keywords: str, n: int = 5, note: str = "", ai_note: bool = False,
            dry_run: bool = True, yes: bool = False):
    """Search + send invites. dry-run ON by default — pass --no-dry-run to arm."""
    if not dry_run and not yes:
        if not typer.confirm(f"ARM: send up to {n} REAL invites?"):
            raise typer.Exit()
    g, store = _guard(dry_run)
    voy = Voyager(g)
    gray = Gray(voy, g, store)
    sent = 0
    try:
        for p in gray.search_people(keywords, n * 2):
            if sent >= n:
                break
            msg = note
            if ai_note:
                msg = content.draft_note(p.name, p.headline, f"shared interest: {keywords}")
            try:
                if gray.send_invite(p, msg, dry_run=dry_run):
                    sent += 1
                    con.print(f"[green]invite[/green] {p.name} {'(dry)' if dry_run else ''}")
            except CapReached as e:
                con.print(f"[yellow]stop: {e}[/yellow]"); break
            except CircuitOpen as e:
                con.print(f"[red]BREAKER: {e}[/red]"); break
    finally:
        voy.close()
    con.print(f"done: {sent} invite(s)")


@app.command()
def message(urn: str, text: str, dry_run: bool = True, yes: bool = False):
    if not dry_run and not yes and not typer.confirm("Send REAL message?"):
        raise typer.Exit()
    g, store = _guard(dry_run)
    voy = Voyager(g)
    try:
        ok = Gray(voy, g, store).send_message(
            Person(urn=urn, public_id="", name=""), text, dry_run=dry_run)
    except (CapReached, CircuitOpen) as e:
        con.print(f"[red]{e}[/red]"); raise typer.Exit(1)
    finally:
        voy.close()
    con.print("sent" if ok else "failed")


# ---- status -----------------------------------------------------------------

@app.command()
def status():
    _, store = _guard(dry_run=True)
    import datetime as dt
    from zoneinfo import ZoneInfo
    now = dt.datetime.now(ZoneInfo(config.Settings.load().timezone))
    t = Table("action", "today", "day cap", "week", "week cap")
    for a in (Action.CONNECT, Action.MESSAGE, Action.SEARCH):
        day = store.count_since(a.value, now - dt.timedelta(days=1))
        week = store.count_since(a.value, now - dt.timedelta(days=7))
        t.add_row(a.value, str(day), str(CAPS[a]["per_day"]),
                  str(week), str(CAPS[a]["per_week"]))
    con.print(t)
    con.rule("recent")
    for ts, action, target, ok, note in store.recent(10):
        mark = "[green]ok[/green]" if ok else "[red]x[/red]"
        con.print(f"{ts[:19]} {mark} {action} {target[-12:]} {note[:30]}")


if __name__ == "__main__":
    app()

"""
voyager.py — the gray-half actions: search / connect / message.

These use LinkedIn's private Voyager endpoints. They are NOT sanctioned by
LinkedIn's User Agreement. Every call routes through Guard.check() first and
Guard.human_pause() after, and results are deduped via Store.

NOTE ON ENDPOINT DRIFT: Voyager paths change without notice. The paths below
match the web client as of writing; expect to update them. They are isolated
here on purpose so a break is a one-file fix, not a rewrite.
"""
from __future__ import annotations

from dataclasses import dataclass

from .safety import Action, Guard
from .session import Voyager
from .store import Store


@dataclass
class Person:
    urn: str            # e.g. "urn:li:fsd_profile:ACoAAB..."
    public_id: str
    name: str
    headline: str = ""


class Gray:
    def __init__(self, voy: Voyager, guard: Guard, store: Store):
        self.voy = voy
        self.guard = guard
        self.store = store

    # ---- search -------------------------------------------------------------

    def search_people(self, keywords: str, limit: int = 10) -> list[Person]:
        self.guard.check(Action.SEARCH)
        params = {
            "decorationId": "com.linkedin.voyager.dash.deco.search.SearchClusterCollection-165",
            "origin": "GLOBAL_SEARCH_HEADER",
            "q": "all",
            "query": (
                "(keywords:%s,flagshipSearchIntent:SEARCH_SRP,"
                "queryParameters:(resultType:List(PEOPLE)))" % keywords
            ),
            "start": 0,
            "count": limit,
        }
        r = self.voy.get("/graphql", params=params)
        self.guard.record(Action.SEARCH, target=keywords, ok=r.is_success)
        self.guard.human_pause(Action.SEARCH)
        if not r.is_success:
            return []
        return self._parse_people(r.json(), limit)

    # ---- connect ------------------------------------------------------------

    def send_invite(self, person: Person, note: str = "", dry_run: bool = False) -> bool:
        if self.store.already_contacted(person.urn, "connect"):
            return False  # never double-invite
        self.guard.check(Action.CONNECT)

        if dry_run:
            self.guard.record(Action.CONNECT, target=person.urn, ok=True, note="DRY")
            self.store.mark_contacted(person.urn, "connect")
            return True

        body = {"invitee": {"inviteeUnion": {"memberProfile": person.urn}}}
        if note:
            body["customMessage"] = note[:300]   # LinkedIn hard limit
        r = self.voy.post(
            "/growth/normInvitations",
            json=body,
            headers={"content-type": "application/json"},
        )
        ok = r.is_success
        self.guard.record(Action.CONNECT, target=person.urn, ok=ok,
                          note="" if ok else r.text[:120])
        if ok:
            self.store.mark_contacted(person.urn, "connect")
        self.guard.human_pause(Action.CONNECT)
        return ok

    # ---- message ------------------------------------------------------------

    def send_message(self, person: Person, text: str, dry_run: bool = False) -> bool:
        self.guard.check(Action.MESSAGE)
        if dry_run:
            self.guard.record(Action.MESSAGE, target=person.urn, ok=True, note="DRY")
            return True

        body = {
            "message": {"body": {"text": text, "attributes": []}},
            "recipients": [person.urn],
        }
        r = self.voy.post(
            "/voyagerMessagingDashMessengerMessages?action=createMessage",
            json=body,
            headers={"content-type": "application/json"},
        )
        ok = r.is_success
        self.guard.record(Action.MESSAGE, target=person.urn, ok=ok,
                          note="" if ok else r.text[:120])
        self.guard.human_pause(Action.MESSAGE)
        return ok

    # ---- parsing ------------------------------------------------------------

    @staticmethod
    def _parse_people(payload: dict, limit: int) -> list[Person]:
        """Voyager search JSON is deeply nested and drifts. Keep parsing
        defensive: pull what we can, skip what we can't."""
        out: list[Person] = []
        for el in payload.get("included", []):
            urn = el.get("entityUrn", "")
            if "fsd_profile" not in urn:
                continue
            name = " ".join(
                filter(None, [el.get("firstName"), el.get("lastName")])
            ) or el.get("title", {}).get("text", "")
            out.append(Person(
                urn=urn,
                public_id=el.get("publicIdentifier", ""),
                name=name,
                headline=el.get("headline", {}).get("text", "")
                if isinstance(el.get("headline"), dict) else "",
            ))
            if len(out) >= limit:
                break
        return out

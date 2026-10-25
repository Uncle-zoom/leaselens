"""AI results for the page: saved results in demo mode, live agents otherwise, never an exception on the page."""
from __future__ import annotations

import agent_store
import analysis
from facts import FactSheet
from guardrails import Budget, BudgetExceeded


def saved_address(address: str) -> dict | None:
    return agent_store.load("address", address)


def saved_recommendation(addresses: list[str]) -> dict | None:
    return agent_store.load("recommendation", agent_store.recommendation_key(addresses))


class LiveHandle:
    """A running AI analysis for the page: poll snapshot_json() until it says done."""

    def __init__(self, run, budget: Budget):
        self.run, self.budget = run, budget

    @property
    def done(self) -> bool:
        return self.run.done

    def progress(self) -> dict[tuple[str, str], bool]:
        return {k: f.done() for k, f in self.run.futures.items()}

    def snapshot_json(self) -> dict:
        """The same JSON shape that is saved to disk, plus `errors`, `done` and `run` (tokens, dollars so far)."""
        snap = self.run.snapshot()
        addresses = {}
        for s in self.run.sheets:
            per = snap["addresses"][s.address]
            addresses[s.address] = {
                "block": per["block"].to_dict() if "block" in per else None,
                "landlord": per["landlord"].to_dict() if "landlord" in per else None,
                "email_ask_questions": per["email"].to_dict() if "email" in per else None,
                "email_negotiate": None, "chat_examples": [], "priorities": None}
        rec = snap["recommendation"].to_dict() if snap["recommendation"] else None
        return {"addresses": addresses, "recommendation": rec, "errors": snap["errors"], "source": "live", "done": snap["done"],
                "single_address": len(self.run.sheets) == 1,
                "run": {"requests": self.budget.requests, "tokens": self.budget.tokens, "usd": round(self.budget.usd, 6)}}


def start_live(sheets: list[FactSheet], session: Budget, run_caps: dict | None = None) -> LiveHandle:
    """Start the specialists in parallel and return at once (see team.Team.start)."""
    import team
    run = Budget("this run", **(run_caps or team.RUN_CAPS))
    return LiveHandle(team.Team(session=session).start(sheets, run), run)


def run_live(sheets: list[FactSheet], session: Budget, run_caps: dict | None = None) -> dict:
    """Blocking version: start, wait for everything, return the final snapshot."""
    h = start_live(sheets, session, run_caps)
    h.run.wait()
    return h.snapshot_json()


def ask(sheet: FactSheet, question: str, history: list | None, session: Budget) -> tuple[dict, list | None]:
    """One chat turn. Returns ({"answer", "known", "sources", "removed", "error"}, new_history)."""
    import team
    try:
        t = team.Team(session=session)
        checked, history = t.chat(sheet, question, history, Budget("this question", **team.CHAT_CAPS))
        d = checked.to_dict()
        return {**d["output"], "removed": d["removed"], "error": None, "tokens": d["tokens"], "usd": d["usd"]}, history
    except BudgetExceeded as exc:
        return {"answer": "", "known": False, "sources": [], "removed": [], "error": str(exc)}, history
    except Exception as exc:
        return {"answer": "", "known": False, "sources": [], "removed": [],
                "error": f"The AI assistant is unavailable right now ({type(exc).__name__}). Your data is unaffected."}, history


def negotiate(sheet: FactSheet, session: Budget, tone: str = "friendly") -> tuple[dict | None, str | None]:
    import team
    try:
        c = team.Team(session=session).negotiator(sheet, Budget("this email", **team.CHAT_CAPS), "negotiate", tone)
        return c.to_dict(), None
    except BudgetExceeded as exc:
        return None, str(exc)
    except Exception as exc:
        return None, f"The AI assistant is unavailable right now ({type(exc).__name__})."


def all_removals(d: dict | None) -> list[dict]:
    out = []
    for key in ("block", "landlord", "email_ask_questions", "email_negotiate", "email_negotiate_firm"):
        part = (d or {}).get(key)
        if part:
            out += part.get("removed", [])
    return out

"""Ask First Pay demo: customer chat, owner phone page, ledger page, scenario buttons.

Money moves only through `ask_first_pay.gate`. The chat goes to the real agent
(`ask_first_pay.agent.run_turn`, see `front.py`), which gets an `AgentGate` and a `HoldDesk`;
the owner page gets `OwnerSide`. Nothing in this package calls the provider's money methods.
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path

from ask_first import MandateRejected, generate_pair, public_key_hex
from ask_first.canonical import canonical
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..fake_provider import FakeProvider
from ..agent.tools import SLOTS
from ..gate import AgentGate, HoldDesk, OwnerSide, make_engine
from .front import BUSINESS, GOODWILL_REFUND, SLOT_LABELS, AgentFrontDesk

HERE = Path(__file__).parent
PAIRING_TTL_S = 3600
# The owner's headline is chosen by the SIGNED action and filled with the SIGNED cap: plain words,
# still nothing the model wrote.
HEADLINES = {"capture_deposit": "Keep up to ${cap} of the held deposit (no-show)",
             "void_deposit": "Release the held deposit; nothing is charged (cancellation)",
             "refund_deposit": "Give back up to ${cap} of the captured deposit (goodwill)"}


class DemoState:
    def __init__(self, provider=None, ledger_path: str | None = None, model_factory=None) -> None:
        self.provider = provider if provider is not None else FakeProvider()
        self.simulated = hasattr(self.provider, "approve")      # only the fake lets us play the payer
        if ledger_path is None:
            ledger_path = os.environ.get("ASK_FIRST_DEMO_LEDGER") or str(
                Path(tempfile.mkdtemp(prefix="ask-first-demo-")) / "ledger.jsonl")
        # Until a phone pairs, the person's key belongs to nobody: no one can approve anything.
        self.engine = make_engine(self.provider, generate_pair()[1], ledger_path)
        self.agent = AgentGate(self.engine)
        self.owner = OwnerSide(self.engine)
        self.desk = HoldDesk(self.provider)
        self.front = AgentFrontDesk(self.agent, self.desk, self.checkout_url, model_factory)
        self.paired_key: str | None = None
        self.declined: set[str] = set()
        self.scenario_used: set[str] = set()   # held bookings a scenario already acted on
        self.lock = threading.RLock()

    def checkout_url(self, order_id: str) -> str:
        if self.simulated:
            return f"/checkout/{order_id}"
        return self.front.approve_urls.get(order_id, "/chat#end")     # PayPal's own payer page

    def new_pairing_code(self) -> str:
        return self.owner.new_pairing_code(PAIRING_TTL_S)

    # ---- scenarios (each one is self-contained with the fake provider)
    def _booking_for_scenario(self):
        """(conversation, booking) with a held deposit, made through the agent like a customer would."""
        held = self.front.latest("deposit_held")
        if (held is not None and held[1]["id"] not in self.scenario_used
                and not any(m["booking_id"] == held[1]["id"] for m in held[0].mandates.values())):
            self.scenario_used.add(held[1]["id"])      # the booking the customer just made in the chat
            return held
        if self.simulated:
            slot = self.front.free_slot()
            if slot is None:                          # every slot taken: a new customer conversation
                self.front.new_conversation()
                slot = self.front.free_slot()
            self.front.handle(f"Hi, please book {SLOT_LABELS[[*SLOTS].index(slot)]}")
            found = self.front.latest("booked")
            if found is None:
                return None
            s, b = found
            self.provider.approve(b["order_id"])      # the payer approves on the checkout page
            self.front.on_payer_approved(b["order_id"])
            self.scenario_used.add(b["id"])
            return found if b["status"] == "deposit_held" else None
        found = self.front.latest("deposit_held")
        if found is None:
            self.front.say("Book through the chat and approve the deposit on PayPal first.", who="system")
        return found

    def scenario(self, kind: str) -> bool:
        with self.lock:
            if kind == "cancel":
                self.front.say("Scenario: cancellation", who="system")
                if self._booking_for_scenario() is None:
                    return False
                self.front.handle("I need to cancel, sorry.")
            elif kind in ("no_show", "goodwill"):
                self.front.say("Scenario: no-show" + (" with goodwill refund" if kind == "goodwill" else ""), who="system")
                found = self._booking_for_scenario()
                if found is None:
                    return False
                s, b = found
                self.front.no_show(s, b["id"], GOODWILL_REFUND if kind == "goodwill" else None)
            else:
                return False
            return True

    # ---- owner side
    def mandate_rows(self) -> list[dict]:
        """Every mandate the agent asked for, with the owner-facing text built from signed fields."""
        rows = []
        for jti in list(self.owner.pending):
            m = self.owner.get(jti)
            if m is None:
                continue
            state = "declined" if jti in self.declined and m["_state"] == "pending" else m["_state"]
            rows.append({"id": jti, "short": jti[:8], "state": state, "action": m["action"],
                         "headline": HEADLINES.get(m["action"], m["action"]).format(cap=f"{m['cap']:.2f}"),
                         "resource": m["recipient"], "cap": f"{m['cap']:.2f}", "exp": m["exp"],
                         "exp_text": time.strftime("%H:%M:%S UTC", time.gmtime(m["exp"])),
                         "description": self.agent.describe(jti),
                         "canonical": canonical(self.owner.pending[jti]).decode("utf-8")})
        return rows

    def approve(self, mandate_id: str, signature: str) -> None:
        """Only a mandate still waiting can be approved: a decline is final, and approving twice
        is refused instead of silently answering ok."""
        with self.lock:
            m = self.owner.get(mandate_id)
            if m is not None and mandate_id in self.declined:
                raise MandateRejected("declined", f"{mandate_id} was declined by the owner; declines are final")
            if m is not None and m["_state"] != "pending":
                raise MandateRejected("already_approved", f"{mandate_id} is already {m['_state']}")
            self.owner.approve(mandate_id, signature)
            self.front.on_approved(mandate_id)

    def decline(self, mandate_id: str) -> bool:
        with self.lock:
            m = self.owner.get(mandate_id)
            if m is None or m["_state"] != "pending":
                return False
            self.declined.add(mandate_id)
            self.front.on_declined(mandate_id)
            return True

    def ledger_rows(self) -> tuple[list[dict], dict]:
        led = self.agent.view_ledger()
        rows = []
        for e in reversed(led["entries"]):
            if "_unreadable" in e:
                continue
            # A rejected row records only the reason; show what that mandate was for (its signed
            # fields), so "rejected · replay" reads as "a second capture of AUTH-… was refused".
            m = self.owner.get(str(e.get("mandate_id", ""))) or {}
            amount = e["amount"] if "amount" in e else m.get("cap")
            rows.append({"n": e.get("n"), "time": time.strftime("%H:%M:%S", time.gmtime(e.get("ts", 0))),
                         "result": e.get("result"), "reason": e.get("reason") or "",
                         "mandate": str(e.get("mandate_id", ""))[:8],
                         "action": e.get("action") or m.get("action", ""),
                         "resource": e.get("recipient") or m.get("recipient", ""),
                         "amount": f"{amount:.2f}" if amount is not None else "",
                         "hash": e.get("hash", "")})
        v = dict(led["verification"])
        v["empty"] = not led["entries"]
        return rows, v


def default_provider():
    """FakeProvider unless PayPal sandbox credentials are set and the adapter module exists."""
    if os.environ.get("PAYPAL_CLIENT_ID"):
        try:
            from ask_first_pay.paypal import PayPalProvider
            return PayPalProvider()
        except Exception as e:                          # noqa: BLE001
            print(f"[demo] PayPalProvider unavailable ({e!r}); using FakeProvider")
    return FakeProvider()


async def _json(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def create_app(provider=None, ledger_path: str | None = None, model_factory=None) -> FastAPI:
    """`model_factory(conversation_state) -> model`; default: Claude with a key, else offline."""
    state = DemoState(provider if provider is not None else default_provider(), ledger_path, model_factory)
    app = FastAPI(title="Ask First Pay demo")
    app.state.demo = state
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")

    def page(request: Request, name: str, **ctx):
        base = {"business": BUSINESS, "state": state, "simulated": state.simulated}
        return templates.TemplateResponse(request, name, {**base, **ctx})

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return page(request, "index.html", nav="home")

    # ---- customer chat
    @app.get("/chat", response_class=HTMLResponse)
    def chat(request: Request):
        return page(request, "chat.html", nav="chat", messages=state.front.messages, slots=SLOT_LABELS,
                    model_name=state.front.model_name)

    @app.post("/chat/send")
    async def chat_send(request: Request):
        # Parsed by hand: python-multipart is not a declared dependency and a plain
        # urlencoded form needs nothing more.
        fields = parse_qs((await request.body()).decode("utf-8", "replace"))
        message = (fields.get("message") or [""])[0][:500]
        with state.lock:
            state.front.handle(message)
        return RedirectResponse("/chat#end", status_code=303)

    @app.get("/checkout/{order_id}", response_class=HTMLResponse)
    def checkout(request: Request, order_id: str):
        order = getattr(state.provider, "orders", {}).get(order_id) if state.simulated else None
        if order is None:
            return RedirectResponse(f"/chat", status_code=303)
        return page(request, "checkout.html", nav="chat", order=order)

    @app.post("/checkout/{order_id}/approve")
    def checkout_approve(order_id: str):
        if state.simulated and order_id in state.provider.orders:
            with state.lock:
                state.provider.approve(order_id)
                state.front.on_payer_approved(order_id)
        return RedirectResponse("/chat#end", status_code=303)

    # ---- scenarios
    @app.post("/scenario/{kind}")
    def scenario(kind: str):
        ok = state.scenario(kind)
        return RedirectResponse("/owner" if ok else "/chat#end", status_code=303)

    @app.post("/replay")
    def replay():
        with state.lock:
            state.front.replay_last()
        return RedirectResponse("/ledger", status_code=303)

    # ---- owner phone
    @app.get("/owner", response_class=HTMLResponse)
    def owner(request: Request):
        rows = state.mandate_rows()
        return page(request, "owner.html", nav="owner", rows=rows,
                    pending=[r for r in rows if r["state"] == "pending"], paired=state.paired_key)

    @app.get("/owner/api/mandates")
    def owner_api():
        return {"paired": state.paired_key, "mandates": state.mandate_rows()}

    @app.post("/owner/pair")
    async def owner_pair(request: Request):
        body = await _json(request)
        try:
            with state.lock:
                state.paired_key = state.owner.pair(str(body.get("code", "")).strip(),
                                                    str(body.get("public_key", "")))
        except MandateRejected as e:
            return JSONResponse({"ok": False, "reason": e.reason, "detail": e.detail}, status_code=400)
        return {"ok": True, "public_key": state.paired_key}

    @app.post("/owner/approve")
    async def owner_approve(request: Request):
        body = await _json(request)
        try:
            state.approve(str(body.get("mandate_id", "")), str(body.get("signature", "")))
        except MandateRejected as e:
            return JSONResponse({"ok": False, "reason": e.reason, "detail": e.detail}, status_code=400)
        return {"ok": True}

    @app.post("/owner/decline")
    async def owner_decline(request: Request):
        body = await _json(request)
        ok = state.decline(str(body.get("mandate_id", "")))
        return JSONResponse({"ok": ok}, status_code=200 if ok else 400)

    # ---- ledger
    @app.get("/ledger", response_class=HTMLResponse)
    def ledger(request: Request):
        rows, verification = state.ledger_rows()
        return page(request, "ledger.html", nav="ledger", rows=rows, v=verification)

    return app

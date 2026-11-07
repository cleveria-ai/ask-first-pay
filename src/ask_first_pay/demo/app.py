"""Ask First Pay demo: customer chat, owner phone page, ledger page, scenario buttons.

Money moves only through `ask_first_pay.gate`. The chat goes to the real agent
(`ask_first_pay.agent.run_turn`, see `front.py`), which gets an `AgentGate` and a `HoldDesk`;
the owner page gets `OwnerSide`. Nothing in this package calls the provider's money methods.
"""
from __future__ import annotations

import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from dataclasses import asdict

from ask_first import MandateRejected, generate_pair, public_key_hex
from ask_first.keys import public_key_from_hex
from ask_first.canonical import canonical
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..fake_provider import FakeProvider
from ..paypal.webhooks import MAX_BODY, CertVerifier, WebhookReceiver, WebhookRejected, WebhookSimulator, fetch_paypal_cert
from ..agent.state import AgentState
from ..agent.tools import SLOTS
from ..store import SqliteStore
from ..gate import AgentGate, HoldDesk, OwnerSide, make_engine
from . import happened, owner_view
from .front import BUSINESS, GOODWILL_REFUND, SLOT_LABELS, AgentFrontDesk, Message

HERE = Path(__file__).parent
PAIRING_TTL_S = 3600
# The owner's headline is chosen by the SIGNED action and filled with the SIGNED cap: plain words,
# still nothing the model wrote.
# (owner_view.card has the words.)
STATE_TONE = {"pending": "warn", "approved": "info", "used": "ok", "declined": "bad", "expired": "neutral"}
SIGNED_FIELDS = ("jti", "iss", "sub", "action", "recipient", "cap", "created", "exp", "plan_hash")
SCENARIO_LABELS = {"no_show": "no-show", "cancel": "cancellation", "goodwill": "no-show with goodwill refund"}
ORDER_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")      # PayPal's ?token= on return_url / cancel_url


def video_safe() -> bool:
    """ASK_FIRST_VIDEO=1: no third-party brand but PayPal on screen (contest rule on marks)."""
    return os.environ.get("ASK_FIRST_VIDEO", "").strip() in ("1", "true", "yes")


def model_label(model_name: str, video: bool) -> str:
    if not video:
        return model_name
    return "offline scripted model" if model_name == "offline scripted model" else "live LLM, tool use"


class DemoState:
    def __init__(self, provider=None, ledger_path: str | None = None, model_factory=None,
                 store: SqliteStore | None = None) -> None:
        self.provider = provider if provider is not None else FakeProvider()
        self.simulated = hasattr(self.provider, "approve")      # only the fake lets us play the payer
        self.store = store
        if ledger_path is None and store is not None:
            ledger_path = store.ledger_path                     # the ledger survives restarts too
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
        self.owner_keys: list[str] = []        # every key this shop paired: old approvals stay verifiable
        self.paypal_results: dict[str, dict] = {}   # mandate jti -> the id PayPal returned for it
        self.declined: set[str] = set()
        self.scenario_used: set[str] = set()   # held bookings a scenario already acted on
        self.lock = threading.RLock()
        self.last: dict | None = None          # the "what just happened" line (demo/happened.py)
        self.webhook_sim, self.webhooks = self._webhooks()
        # The head of the ledger, remembered OUTSIDE the ledger file: the only way a hash chain can
        # reveal rows cut off its end (or a whole chain recomputed by someone with file access).
        self.ledger_head: dict | None = None
        self._track_ledger_head()
        if store is not None and (snap := store.load()) is not None:
            self.restore(snap)
        self.engine.executor = self._recording(self.engine.executor)
        if store is not None:
            self.engine.executor = self._saved_before(self.engine.executor)

    def _track_ledger_head(self) -> None:
        ledger = self.engine.ledger
        last = next(iter(reversed(ledger.entries())), None)
        if last and "hash" in last:
            self.ledger_head = {"n": last["n"], "hash": last["hash"]}
        append = ledger.append

        def tracked(row, *args, **kw):
            out = append(row, *args, **kw)
            if "hash" in out and not out.get("out_of_chain"):
                self.ledger_head = {"n": out["n"], "hash": out["hash"]}
            return out
        ledger.append = tracked

    def _recording(self, executor):
        """Remember what PayPal answered for each mandate (capture id, refund id, voided hold), so
        the ledger detail can show one tap -> one PayPal-Request-Id -> one PayPal id."""
        def run(mandate, requested):
            out = executor(mandate, requested)
            found = owner_view.paypal_result(requested.get("action"), out)
            if found:
                self.paypal_results[mandate["jti"]] = found
            return out
        return run

    def _saved_before(self, executor):
        """The engine marks a mandate used, then calls PayPal. Save that mark first, so a crash
        during the call cannot leave an approved-but-unused mandate on disk."""
        def run(mandate, requested):
            if not self.store.claim_mandate(mandate["jti"]):      # shared by every process on this database
                raise RuntimeError("this mandate was already spent (claimed in the database)")
            self.persist()
            return executor(mandate, requested)
        return run

    @contextmanager
    def action(self, label: str):
        """Run one user action and record what it changed for the "what just happened" line.
        The caller may change `box["label"]` once it knows the outcome."""
        with self.lock:
            before = happened.mark(self)
            box = {"label": label}
            try:
                yield box
            finally:
                self.last = happened.describe(self, box["label"], before)

    # ---- optional persistence (ASK_FIRST_DB): see ask_first_pay/store.py
    def snapshot(self) -> dict:
        e, f = self.engine, self.front
        return {"version": 1, "simulated": self.simulated,
                "engine": {"pending": e.pending, "approved": e.approved, "used": sorted(e.used)},
                "ledger_head": self.ledger_head,
                "paired_key": self.paired_key, "owner_keys": list(self.owner_keys),
                "paypal_results": dict(self.paypal_results), "declined": sorted(self.declined),
                "scenario_used": sorted(self.scenario_used),
                "front": {"messages": [asdict(m) for m in f.messages],
                          "conversations": [asdict(s) for s in f.conversations],
                          "linked": sorted(f._linked), "approve_urls": f.approve_urls,
                          "goodwill": f.goodwill, "turns": f.turns},
                "provider": self.provider.to_dict() if hasattr(self.provider, "to_dict") else None}

    def restore(self, snap: dict) -> None:
        """Back to the saved state. Approvals are restored as signed: the engine re-verifies each
        signature against the paired key when the mandate is executed, as always."""
        if snap.get("version") != 1:
            raise ValueError(f"unknown snapshot version {snap.get('version')!r}")
        if snap.get("simulated") != self.simulated:
            raise ValueError("this database was written with a different payment provider")
        e, f = self.engine, self.front
        # In place: OwnerSide and AgentGate hold references to these very containers.
        e.pending.clear()
        e.pending.update({k: dict(v) for k, v in snap["engine"]["pending"].items()})
        e.approved.clear()
        e.approved.update({k: {"mandate": dict(v["mandate"]), "signature": v["signature"]}
                           for k, v in snap["engine"]["approved"].items()})
        # Used = what the snapshot says, plus anything the ledger shows was executed or failed
        # (a crash between the PayPal call and the save must not reopen that mandate).
        if snap.get("ledger_head"):
            self.ledger_head = dict(snap["ledger_head"])
        e.used.update(set(snap["engine"]["used"]) | self.store.used_mandates() | {str(r.get("mandate_id")) for r in e.ledger.entries()
                                                if r.get("result") in ("executed", "failed")})
        self.paired_key = snap["paired_key"]
        if self.paired_key:
            e.person_pub = public_key_from_hex(self.paired_key)
        self.owner_keys = [str(k) for k in snap.get("owner_keys") or ([self.paired_key] if self.paired_key else [])]
        self.paypal_results = {str(k): dict(v) for k, v in (snap.get("paypal_results") or {}).items()}
        self.declined, self.scenario_used = set(snap["declined"]), set(snap["scenario_used"])
        fr = snap["front"]
        f.messages = [Message(**m) for m in fr["messages"]]
        f.conversations, f._models = [], {}
        for s in fr["conversations"]:
            st = AgentState(**s)
            f.conversations.append(st)
            f._models[id(st)] = f.model_factory(st)
        f._linked, f.approve_urls = set(fr["linked"]), dict(fr["approve_urls"])
        f.goodwill, f.turns = {k: float(v) for k, v in fr["goodwill"].items()}, int(fr["turns"])
        if snap.get("provider") is not None and hasattr(self.provider, "load_dict"):
            self.provider.load_dict(snap["provider"])

    def persist(self) -> None:
        if self.store is not None:
            with self.lock:
                self.store.save(self.snapshot())

    # ---- PayPal webhooks (they can hold a deposit, never move money)
    def _webhooks(self):
        """With the fake provider, a local simulator plays PayPal and signs its events; with the
        sandbox, PAYPAL_WEBHOOK_ID turns on verification against PayPal's certificate. With
        neither, the receiver is off and the customer still says "I paid" in the chat."""
        handlers = {"CHECKOUT.ORDER.APPROVED": self._on_order_approved,
                    "PAYMENT.AUTHORIZATION.VOIDED": self._on_authorization("voided"),
                    "PAYMENT.AUTHORIZATION.EXPIRED": self._on_authorization("expired"),
                    "PAYMENT.CAPTURE.COMPLETED": self._note("a capture completed"),
                    "PAYMENT.CAPTURE.REFUNDED": self._note("a refund completed")}
        dedupe = {}
        if self.store is not None:
            def remember(event_id, event_type, outcome):
                self.persist()                 # the handler's effect is saved before "seen":
                self.store.remember_event(event_id, event_type, outcome)   # a crash means redelivery
            dedupe = {"seen": self.store.seen_event, "remember": remember}
        if self.simulated:
            sim = WebhookSimulator()
            return sim, WebhookReceiver(sim.verifier(), handlers, **dedupe)
        webhook_id = os.environ.get("PAYPAL_WEBHOOK_ID")
        if webhook_id:
            return None, WebhookReceiver(CertVerifier(webhook_id, fetch_paypal_cert), handlers, **dedupe)
        return None, None

    def _booking_with(self, key: str, value: str):
        for s in self.front.conversations:
            for b in s.bookings.values():
                if value and b.get(key) == value:
                    return s, b
        return None

    def _on_order_approved(self, resource: dict, source: str = "PayPal webhook") -> str:
        """The payer approved an order. Reached from the CHECKOUT.ORDER.APPROVED webhook and from
        the buyer's redirect back to /chat/return, whichever comes first: both run under the lock,
        and only a booking still `booked` is confirmed, so the second arrival is a no-op."""
        found = self._booking_with("order_id", str(resource.get("id", "")))
        if found is None or found[1]["status"] != "booked":
            return "no booking waiting for this order"
        self.front.on_payer_approved(found[1]["order_id"], source=source)
        return found[1]["status"]

    def payer_returned(self, order_id: str) -> str:
        """PayPal sent the buyer back to return_url with ?token=<order id>: the same confirm path as
        the webhook, so a live run needs no webhook tunnel. Authorizing only holds money, and PayPal
        refuses it unless the payer really approved that order."""
        with self.lock:
            return self._on_order_approved({"id": order_id}, source="Back from PayPal")

    def payer_cancelled(self, order_id: str) -> bool:
        with self.lock:
            found = self._booking_with("order_id", order_id)
            if found is None or found[1]["status"] != "booked":
                return False
            self.front.say("The customer left PayPal without approving. Nothing is held.", who="system")
            return True

    def _on_authorization(self, what: str):
        def handle(resource: dict) -> str:
            found = self._booking_with("authorization_id", str(resource.get("id", "")))
            if found is None:
                return "no booking holds this authorization"
            s, b = found
            # A note only: a webhook never changes what the agent may ask for (PayPal itself
            # refuses a capture on an expired hold).
            self.front.say(f"PayPal webhook: the hold {b['authorization_id']} for {b['id']} was {what}.", who="system")
            return "noted"
        return handle

    def _note(self, what: str):
        def handle(resource: dict) -> str:
            self.front.say(f"PayPal webhook: {what} ({resource.get('id', '?')}).", who="system")
            return "noted"
        return handle

    def receive_webhook(self, headers: dict, body: bytes) -> dict:
        if self.webhooks is None:
            raise WebhookRejected("not_configured", "set PAYPAL_WEBHOOK_ID to receive sandbox webhooks")
        with self.lock:
            return self.webhooks.receive(headers, body)

    def payer_approved_on_checkout(self, order_id: str) -> None:
        """The simulated checkout: the payer approves, and the simulated PayPal tells us so with
        a signed CHECKOUT.ORDER.APPROVED webhook, the same path the sandbox uses."""
        with self.lock:
            self.provider.approve(order_id)
            headers, body = self.webhook_sim.event("CHECKOUT.ORDER.APPROVED", {"id": order_id, "status": "APPROVED"})
            self.receive_webhook(headers, body)

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
            self.payer_approved_on_checkout(b["order_id"])   # the payer approves; PayPal's webhook says so
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
    def pair(self, code: str, public_key: str) -> str:
        self.paired_key = self.owner.pair(code, public_key)
        if self.paired_key not in self.owner_keys:
            self.owner_keys.append(self.paired_key)
        return self.paired_key

    def mandate_rows(self) -> list[dict]:
        """Every mandate the agent asked for, oldest first (it expires first), with the owner-facing
        text built from signed fields and the booking that owns the signed PayPal resource."""
        rows = []
        entries = self.agent.view_ledger()["entries"]
        for jti in list(self.owner.pending):
            m = self.owner.get(jti)
            if m is None:
                continue
            state = "declined" if jti in self.declined and m["_state"] == "pending" else m["_state"]
            if state == "pending" and int(time.time()) > int(m["exp"]):
                state = "expired"                       # the gate would refuse it: do not offer Approve
            c = owner_view.card(m, owner_view.booking_for(self.front, m["recipient"]))
            rows.append({"id": jti, "short": jti[:8], "state": state, "action": m["action"],
                         "kicker": c["kicker"], "headline": c["headline"], "chip": c["chip"], "who": c["who"],
                         "resource": m["recipient"], "cap": f"{m['cap']:.2f}", "cap_text": c["cap_text"],
                         "exp": m["exp"], "exp_left": c["exp_left"],
                         "exp_text": f"{c['exp_clock']} ({c['exp_left'] if c['exp_left'] == 'expired' else 'in ' + c['exp_left']})",
                         "description": self.agent.describe(jti),
                         "canonical": canonical(self.owner.pending[jti]).decode("utf-8"),
                         "tone": STATE_TONE.get(state, "neutral"),
                         "created_text": c["created_clock"],
                         "plan_hash": m.get("plan_hash", ""),
                         "paypal": owner_view.paypal_text(self.paypal_results.get(jti)),
                         "ledger": [e.get("n") for e in entries if e.get("mandate_id") == jti]})
        return rows

    def today(self) -> dict:
        return owner_view.today(self)

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
            mid = str(e.get("mandate_id", ""))
            paid = self.paypal_results.get(mid) if e.get("result") == "executed" else None
            rows.append({"n": e.get("n"), "time": time.strftime("%H:%M:%S", time.gmtime(e.get("ts", 0))),
                         "result": e.get("result"), "reason": e.get("reason") or "",
                         "mandate": str(e.get("mandate_id", ""))[:8],
                         "action": e.get("action") or m.get("action", ""),
                         "resource": e.get("recipient") or m.get("recipient", ""),
                         "amount": f"{amount:.2f}" if amount is not None else "",
                         "hash": e.get("hash", ""),
                         # for the row detail: the full ids, the chain link and the signed fields
                         "mandate_id": str(e.get("mandate_id", "")), "prev": e.get("prev", ""),
                         "plan_hash": e.get("plan_hash", ""),
                         "ts_iso": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(e.get("ts", 0))),
                         "tone": "ok" if e.get("result") == "executed" else "bad",
                         # the gate called PayPal (executed or failed) with the mandate jti as the
                         # PayPal-Request-Id; a rejected attempt never reached PayPal
                         "request_id": mid if e.get("result") in ("executed", "failed") else "",
                         "paypal_id": owner_view.paypal_text(paid),
                         "signed": {k: m[k] for k in SIGNED_FIELDS if k in m}})
        v = dict(led["verification"])
        head = self.ledger_head
        if v["ok"] and head:
            row = next((e for e in led["entries"] if e.get("n") == head["n"]), None)
            if row is None or row.get("hash") != head["hash"]:
                v.update(ok=False, kind="truncated", broken_at=None,
                         message=f"the last row this server wrote (n={head['n']}) is missing or changed: "
                                 f"rows were removed from the end, or the chain was rewritten")
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


def default_store() -> SqliteStore | None:
    """SQLite only when ASK_FIRST_DB names a file; memory otherwise (the default)."""
    path = os.environ.get("ASK_FIRST_DB")
    return SqliteStore(path, os.environ.get("ASK_FIRST_SHOP", "default")) if path else None


def create_app(provider=None, ledger_path: str | None = None, model_factory=None,
               store: SqliteStore | None = None) -> FastAPI:
    """`model_factory(conversation_state) -> model`; default: Claude with a key, else offline."""
    state = DemoState(provider if provider is not None else default_provider(), ledger_path, model_factory,
                      store if store is not None else default_store())
    app = FastAPI(title="Ask First Pay demo")
    app.state.demo = state

    @app.middleware("http")
    async def persist_after_writes(request: Request, call_next):
        response = await call_next(request)
        if request.method == "POST":
            await run_in_threadpool(state.persist)    # a no-op without ASK_FIRST_DB
        return response
    @app.middleware("http")
    async def same_origin_and_headers(request: Request, call_next):
        # CSRF: a browser always sends Origin on a cross-site POST. Curl, tests and PayPal's server
        # send none and pass; a page on another site cannot press our buttons (decline, scenarios,
        # chat). Approving also needs the owner's signature, which no page of ours can forge.
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if (origin is not None and (origin == "null" or urlparse(origin).netloc != request.headers.get("host", ""))) \
                    or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"ok": False, "reason": "cross_site", "detail": "cross-site request refused"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"            # the one-tap Approve button must not be framed
        response.headers["X-Content-Type-Options"] = "nosniff"
        # same-origin, not no-referrer: under no-referrer Chromium sends `Origin: null` on our own
        # form POSTs, and the CSRF check above would refuse every button on the page.
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        return response
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")

    def page(request: Request, name: str, **ctx):
        video = video_safe()
        base = {"business": BUSINESS, "state": state, "simulated": state.simulated, "last": state.last,
                "video": video, "model_label": model_label(state.front.model_name, video)}
        return templates.TemplateResponse(request, name, {**base, **ctx})

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)                # no icon file, and no 404 in the console

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return page(request, "index.html", nav="home")

    # ---- customer chat
    @app.get("/chat", response_class=HTMLResponse)
    def chat(request: Request):
        return page(request, "chat.html", nav="chat", messages=state.front.messages, slots=SLOT_LABELS)

    @app.post("/chat/send")
    async def chat_send(request: Request):
        # Parsed by hand: python-multipart is not a declared dependency and a plain
        # urlencoded form needs nothing more.
        fields = parse_qs((await request.body()).decode("utf-8", "replace"))
        message = (fields.get("message") or [""])[0][:500]
        if message.strip():
            with state.action(f'You sent "{message.strip()[:80]}"'):
                state.front.handle(message)
        return RedirectResponse("/chat#end", status_code=303)

    # ---- PayPal sends the buyer back here (experience_context.return_url / cancel_url)
    @app.get("/chat/return")
    def chat_return(token: str = ""):
        if ORDER_TOKEN_RE.fullmatch(token):
            with state.action("The customer came back from PayPal") as box:
                out = state.payer_returned(token)
                if out == "no booking waiting for this order":
                    box["label"] += " (nothing to confirm: already held, or not our order)"
            state.persist()                           # a GET that changed state: save it too
        return RedirectResponse("/chat#end", status_code=303)

    @app.get("/chat/cancel")
    def chat_cancel(token: str = ""):
        if ORDER_TOKEN_RE.fullmatch(token):
            with state.action("The customer left PayPal without approving"):
                state.payer_cancelled(token)
            state.persist()
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
            with state.action("The customer approved the hold on the simulated PayPal checkout"):
                state.payer_approved_on_checkout(order_id)
        return RedirectResponse("/chat#end", status_code=303)

    # ---- PayPal webhooks
    @app.post("/webhooks/paypal")
    async def paypal_webhook(request: Request):
        try:
            declared = int(request.headers.get("content-length") or 0)
        except ValueError:
            declared = 0
        if declared > MAX_BODY:
            return JSONResponse({"ok": False, "reason": "too_large", "detail": f"{declared} bytes"}, status_code=413)
        body = await request.body()
        try:
            # off the event loop: an approved order runs a whole agent turn (maybe a model call)
            out = await run_in_threadpool(state.receive_webhook, dict(request.headers), body)
        except WebhookRejected as e:
            code = 503 if e.reason == "not_configured" else 400
            return JSONResponse({"ok": False, "reason": e.reason, "detail": e.detail}, status_code=code)
        return {"ok": True, **out}

    @app.get("/webhooks/paypal/events")
    def paypal_webhook_events():
        return {"enabled": state.webhooks is not None, "simulated": state.webhook_sim is not None,
                "events": list(state.webhooks.log) if state.webhooks else []}

    # ---- scenarios
    @app.post("/scenario/{kind}")
    def scenario(kind: str):
        if kind not in SCENARIO_LABELS:
            return RedirectResponse("/chat#end", status_code=303)
        with state.action(f"Scenario: {SCENARIO_LABELS[kind]}") as box:
            ok = state.scenario(kind)
            if not ok:
                box["label"] += " could not start (no held deposit to act on)"
        return RedirectResponse("/owner" if ok else "/chat#end", status_code=303)

    @app.post("/replay")
    def replay():
        with state.action("The agent tried to use the last executed mandate again") as box:
            if not state.front.replay_last():
                box["label"] = "Replay: nothing was executed yet, so there is nothing to replay"
        return RedirectResponse("/ledger#latest", status_code=303)

    # ---- owner phone
    @app.get("/owner", response_class=HTMLResponse)
    def owner(request: Request):
        rows = state.mandate_rows()
        return page(request, "owner.html", nav="owner", rows=rows, today=state.today(),
                    pending=[r for r in rows if r["state"] == "pending"], paired=state.paired_key)

    @app.get("/owner/api/mandates")
    def owner_api():
        return {"paired": state.paired_key, "mandates": state.mandate_rows()}

    @app.post("/owner/pair")
    async def owner_pair(request: Request):
        body = await _json(request)
        try:
            with state.action("This phone was paired with the shop") as box:
                try:
                    state.pair(str(body.get("code", "")).strip(), str(body.get("public_key", "")))
                except MandateRejected as e:
                    box["label"] = f"Pairing refused: {e.reason}"
                    raise
        except MandateRejected as e:
            return JSONResponse({"ok": False, "reason": e.reason, "detail": e.detail}, status_code=400)
        return {"ok": True, "public_key": state.paired_key}

    @app.post("/owner/approve")
    async def owner_approve(request: Request):
        body = await _json(request)
        mid = str(body.get("mandate_id", ""))
        try:
            with state.action(f"The owner approved mandate {mid[:8]} on their phone") as box:
                try:
                    state.approve(mid, str(body.get("signature", "")))
                except MandateRejected as e:
                    box["label"] = f"The owner's approval of {mid[:8]} was refused: {e.reason}"
                    raise
        except MandateRejected as e:
            return JSONResponse({"ok": False, "reason": e.reason, "detail": e.detail}, status_code=400)
        return {"ok": True}

    @app.post("/owner/decline")
    async def owner_decline(request: Request):
        body = await _json(request)
        mid = str(body.get("mandate_id", ""))
        with state.action(f"The owner declined mandate {mid[:8]}") as box:
            ok = state.decline(mid)
            if not ok:
                box["label"] = f"Decline of {mid[:8]} refused: it is not waiting for the owner"
        return JSONResponse({"ok": ok}, status_code=200 if ok else 400)

    # ---- ledger
    @app.get("/ledger", response_class=HTMLResponse)
    def ledger(request: Request):
        rows, verification = state.ledger_rows()
        return page(request, "ledger.html", nav="ledger", rows=rows, v=verification)

    @app.get("/ledger/entry/{n}")
    def ledger_entry(n: int):
        """One raw ledger row as written (with `hash` and `prev`), so anyone can check the link."""
        for e in state.agent.view_ledger()["entries"]:
            if e.get("n") == n:
                return {"entry": e, "prev_url": f"/ledger/entry/{n - 1}" if e.get("prev") else None}
        return JSONResponse({"ok": False, "reason": "no_such_entry"}, status_code=404)

    return app

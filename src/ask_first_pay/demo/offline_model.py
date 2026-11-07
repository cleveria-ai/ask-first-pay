"""The scripted model the demo uses when there is no ANTHROPIC_API_KEY.

It speaks the same protocol as `AnthropicModel` (`create(system, messages, tools)` returning
text and tool_use blocks), so it drives the very same `run_turn` loop and the very same tools.
It is a small deterministic policy instead of a language model: it reads the newest message,
picks one tool, and turns the tool's result into a reply. It has no more power than Claude has:
everything it does goes through the agent's `Toolbox`, i.e. `AgentGate` and `HoldDesk` only.

It follows the same customer rules as the SYSTEM prompt: it replies in the customer's language
(English or Spanish), books under the name the customer gave, and when a customer asks for the
deposit back after a no-show it asks the clinic with `request_refund`, never promising it.
"""
from __future__ import annotations

import ast
import re
from datetime import datetime

from ..agent.loop import ScriptedModel, text, tool
from ..agent.state import AgentState
from ..agent.tools import SLOTS

NO_SHOW_RE = re.compile(r"(booking-\d+) did not show up", re.I)
PAID_RE = re.compile(r"approved PayPal order ([A-Za-z0-9_-]+)", re.I)
APPROVED_RE = re.compile(r"owner approved mandate ([A-Za-z0-9_-]+)", re.I)
DECLINED_RE = re.compile(r"owner declined mandate ([A-Za-z0-9_-]+)", re.I)
RELAY_RE = re.compile(r"^\[(payments|owner|business)\]")      # notes the demo relays, not the customer

# "I'm Lucía", "my name is Lucía Pérez", "soy Lucía", "me llamo Lucía": one or two capitalized words.
_UP, _LOW = "A-ZÁÉÍÓÚÑÜ", "a-záéíóúñü"
NAME_RE = re.compile(
    rf"(?:^|[^\w])(?i:i['’]?m|i am|my name is|my name's|this is|soy|me llamo|mi nombre es)\s+"
    rf"([{_UP}][{_LOW}'’-]+(?:\s+[{_UP}][{_LOW}'’-]+)?)")
NOT_NAMES = {"sorry", "here", "late", "back", "ready", "fine", "ok", "okay", "not", "so", "very", "calling",
             "writing", "going", "running", "sick", "urgent", "lo", "muy", "la", "el", "yo", "de"}
NO_NAME = "Guest (no name given)"     # never "Customer": the owner sees that the name is missing

SPANISH_RE = re.compile(
    r"[¿¡ñ]|\b(hola|soy|quiero|reservar|reserva|cita|cancelo|cancelar|dep[oó]sito|devuelven|devolver|"
    r"lunes|martes|mi[eé]rcoles|jueves|viernes|por favor|gracias|perd[oó]n|lo siento|hijo|hija|puedo|"
    r"me llamo|turno|agendar|urgencias)\b", re.I)
ES_DAYS = {"lunes": "mon", "lun": "mon", "martes": "tue", "miércoles": "wed", "miercoles": "wed",
           "mié": "wed", "mie": "wed", "jueves": "thu", "jue": "thu", "viernes": "fri", "vie": "fri",
           "sábado": "sat", "sabado": "sat", "domingo": "sun"}
ES_WEEKDAYS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
ES_MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
BOOK_WORDS = ("book", "appointment", "slot", "reserv", "cita", "agendar", "turno")
# Asking for the deposit back (goodwill), in English or Spanish.
DEPOSIT_BACK_EN = re.compile(r"\b(deposit|money)\s+back\b|\brefund\s+(my|the)\s+deposit\b|"
                             r"\b(return|give)\s+(me\s+)?(my|the)\s+(deposit|money)\b", re.I)
DEPOSIT_BACK_ES = re.compile(r"(devuelv|devoluci|reembols)\w*.*(dep[oó]sito|dinero|plata)|"
                             r"(dep[oó]sito|dinero|plata).*(devuelv|devoluci|reembols)", re.I)

STATUS_ES = {"booked": "reservada", "deposit_held": "depósito retenido", "captured": "cobrada",
             "cancelled": "cancelada", "refunded": "reembolsada", "partly_refunded": "reembolsada en parte",
             "hold_ended": "retención terminada"}

# What the customer reads, in their language. The wording after hold / ask / void is G14's.
T = {
    "reserved": {"en": "Reserved {slot}. To confirm, hold a ${dep} deposit (nothing is charged now).",
                 "es": "Reservé {slot}. Para confirmar, deja un depósito de ${dep} retenido (no se cobra nada ahora)."},
    "held": {"en": "Confirmed: {slot}. ${dep} is held, not charged. If you cancel, a person at the clinic releases it.",
             "es": "Confirmado: {slot}. Los ${dep} están retenidos, no cobrados. "
                   "Si cancelas, una persona de la clínica los libera."},
    "asked_clinic": {"en": "I can't move your deposit myself; I've asked the clinic.",
                     "es": "No puedo mover tu depósito yo mismo; ya se lo pedí a la clínica."},
    "sorry": {"en": "I'm sorry to hear that. ", "es": "Lamento mucho lo ocurrido. "},
    "asked_owner": {"en": "I asked the owner to approve. Nothing moves until they do.",
                    "es": "Le pedí a la clínica que lo apruebe. Nada se mueve hasta que lo haga."},
    "voided": {"en": "Done: the hold is released. Nothing was charged, so there is nothing to refund.",
               "es": "Listo: la retención se liberó. No se cobró nada, así que no hay nada que reembolsar."},
    "captured": {"en": "Done: ${amt} captured for the no-show.",
                 "es": "Listo: se cobraron ${amt} por la inasistencia."},
    "refunded": {"en": "Done: ${amt} refunded to the customer.", "es": "Listo: se te devolvieron ${amt}."},
    "declined": {"en": "The owner declined, so the deposit stays where it was and nothing moved.",
                 "es": "La clínica dijo que no, así que el depósito sigue donde estaba y nada se movió."},
    "only_held": {"en": "Your deposit is only held, not charged. If you cancel, a person at the clinic releases it.",
                  "es": "Tu depósito solo está retenido, no cobrado. Si cancelas, una persona de la clínica lo libera."},
    "no_charge": {"en": "I can't find a charged deposit on your booking.",
                  "es": "No encuentro un depósito cobrado en tu reserva."},
    "no_cancel": {"en": "I can't find a confirmed booking to cancel.",
                  "es": "No encuentro una reserva confirmada para cancelar."},
    "which_slot": {"en": 'Which slot suits you? {slots}. Reply with e.g. "book {first}".',
                   "es": '¿Qué horario te queda bien? {slots}. Responde, por ejemplo, "reservar {first}".'},
    "taken": {"en": "That slot is taken. Free: {slots}.", "es": "Ese horario está tomado. Libres: {slots}."},
    "no_money": {"en": "I can't move money myself. Anything beyond the held deposit waits for the owner.",
                 "es": "No puedo mover dinero yo mismo. Todo lo que vaya más allá del depósito retenido "
                       "lo decide la clínica."},
    "help": {"en": 'I can book a visit ("book {first}") or cancel one ("cancel"). '
                   "Anything involving money beyond the held deposit waits for the owner.",
             "es": 'Puedo reservar una visita ("reservar {first}") o cancelarla ("cancelo"). '
                   "Todo lo que vaya más allá del depósito retenido lo decide la clínica."},
    "rejected": {"en": "The gate rejected that: {why}. The attempt is on the ledger.",
                 "es": "La compuerta lo rechazó: {why}. El intento quedó registrado."},
    "error": {"en": "Something went wrong: {why}.", "es": "Algo salió mal: {why}."},
    "no_booking": {"en": "No booking yet.", "es": "Todavía no hay reservas."},
    "status": {"en": "Booking {id} for {slot}: {status}.", "es": "Reserva {id} para {slot}: {status}."},
}


def say(key: str, lang: str, **kw) -> str:
    return T[key].get(lang, T[key]["en"]).format(**kw)


def slot_label(slot: str, lang: str = "en") -> str:
    """'2026-11-17 15:00' -> 'Tue 17 Nov 15:00' (or 'mar 17 nov 15:00' in Spanish)."""
    try:
        d = datetime.strptime(slot, "%Y-%m-%d %H:%M")
    except ValueError:
        return slot
    if lang == "es":
        return f"{ES_WEEKDAYS[d.weekday()]} {d.day:02d} {ES_MONTHS[d.month - 1]} {d:%H:%M}"
    return d.strftime("%a %d %b %H:%M")


def match_slot(message: str) -> str | None:
    low = message.lower()
    for s in SLOTS:                                   # exact slot or exact label (English or Spanish)
        if s in low or slot_label(s).lower() in low or slot_label(s, "es") in low:
            return s
    for es, en in ES_DAYS.items():                    # "lunes 9:00" reads as "mon 9:00"
        low = re.sub(rf"\b{es}\b", en, low)
    times = (re.findall(r"\b(\d{1,2}):(\d{2})\b", low)
             or [(h, "00") for h in re.findall(r"\b(\d{1,2})\s*(?:am|h)\b", low)]
             or [(h, "00") for h in re.findall(r"\ba las (\d{1,2})\b", low)])
    days = [d for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun") if re.search(rf"\b{d}", low)]
    for s in SLOTS:
        lab = slot_label(s).lower()
        t_ok = any(lab.endswith(f"{int(h):02d}:{m}") for h, m in times)
        d_ok = any(lab.startswith(d) for d in days)
        if (t_ok and d_ok) or (t_ok and not days) or (d_ok and not times):
            return s
    return None


def customer_name(message: str) -> str | None:
    """The name a customer gives in a message ("I'm Lucía", "soy Lucía"), or None."""
    for m in NAME_RE.finditer(message):
        words = m.group(1).split()
        if words[0].lower() in NOT_NAMES:
            continue
        if len(words) > 1 and words[1].lower() in NOT_NAMES:
            words = words[:1]
        return " ".join(words)[:40]
    return None


def is_spanish(message: str) -> bool:
    return bool(SPANISH_RE.search(message))


def customer_messages(messages: list) -> list[str]:
    """What the customer typed in this conversation, oldest first (relayed notes left out)."""
    return [m["content"] for m in messages
            if m.get("role") == "user" and isinstance(m.get("content"), str) and not RELAY_RE.match(m["content"])]


def conversation_name(messages: list) -> str | None:
    """The latest name the customer gave in this conversation."""
    for msg in reversed(customer_messages(messages)):
        if name := customer_name(msg):
            return name
    return None


def conversation_lang(messages: list) -> str:
    """The language of the customer's latest message: 'es' or 'en'."""
    said = customer_messages(messages)
    return "es" if said and is_spanish(said[-1]) else "en"


def asks_deposit_back(message: str) -> bool:
    return bool(DEPOSIT_BACK_EN.search(message) or DEPOSIT_BACK_ES.search(message))


def _result(content: str):
    try:
        return ast.literal_eval(content)
    except (ValueError, SyntaxError):
        return {"error": content}


class OfflineFrontDeskModel(ScriptedModel):
    """A rule-based stand-in for Claude. Reads `state` (the conversation it belongs to) only to
    find booking ids; it never touches the gate, the provider or the owner's side."""

    def __init__(self, state: AgentState) -> None:
        super().__init__([])
        self.state = state

    def create(self, *, system, messages, tools):
        self.calls += 1
        last = messages[-1]
        if last["role"] == "user" and isinstance(last["content"], list):
            return self._after_tools(messages)
        return self._on_message(str(last["content"]), messages)

    # ---- a new message (customer, payments relay or owner relay)
    def _latest(self, *statuses):
        for b in reversed(list(self.state.bookings.values())):
            if b["status"] in statuses:
                return b
        return None

    def _on_message(self, msg: str, messages: list) -> list:
        low = msg.lower()
        lang = conversation_lang(messages)
        first = slot_label(SLOTS[0], lang)
        if m := PAID_RE.search(msg):
            b = next((x for x in self.state.bookings.values() if x["order_id"] == m.group(1)), None)
            return [tool("confirm_deposit", "c", booking_id=b["id"])] if b else [text("I can't find that order.")]
        if m := APPROVED_RE.search(msg):
            return [tool("execute_mandate", "x", mandate_id=m.group(1))]
        if DECLINED_RE.search(msg):
            return [text(say("declined", lang))]
        if m := NO_SHOW_RE.search(msg):
            # An old hold is refreshed first (reauthorize after the 3-day honor period), then the
            # capture is asked for on whatever authorization is current.
            return [tool("refresh_hold", "h", booking_id=m.group(1))]
        if re.search(r"\b(i\s+(have\s+)?(paid|approved)|payment (is )?done)\b", low):
            b = self._latest("booked")
            if b is not None and b["order_id"]:
                return [tool("confirm_deposit", "c", booking_id=b["id"])]
        if not RELAY_RE.match(msg) and asks_deposit_back(msg):
            # Goodwill: the customer missed the visit (the deposit was captured) and asks for it
            # back. Ask the clinic for what is still captured, never an amount from the message;
            # the owner decides. Never promise it.
            b = self._latest("captured", "partly_refunded")
            if b is not None:
                left = round(b["captured"] - b.get("refunded", 0.0), 2)
                return [tool("request_refund", "r", booking_id=b["id"], amount=left)]
            if self._latest("deposit_held") is not None:
                return [text(say("only_held", lang))]
            return [text(say("no_charge", lang))]
        if "cancel" in low:
            b = self._latest("deposit_held")
            if b is None:
                return [text(say("no_cancel", lang))]
            return [tool("request_void", "v", booking_id=b["id"])]
        if any(w in low for w in BOOK_WORDS):
            slot = match_slot(msg)
            if slot is None:
                return [text(say("which_slot", lang, first=first,
                                 slots=", ".join(slot_label(s, lang) for s in SLOTS)))]
            return [tool("book_slot", "b", customer=conversation_name(messages) or NO_NAME, slot=slot)]
        if "status" in low or "deposit" in low or "estado" in low:
            return [tool("list_bookings", "l")]
        if re.search(r"refund|capture|charge|reembols|devol|cobr", low):
            return [text(say("no_money", lang))]
        return [text(say("help", lang, first=first))]

    # ---- the result of the tool the model just called
    def _after_tools(self, messages) -> list:
        uses = [b for b in messages[-2]["content"] if b.get("type") == "tool_use"]
        results = [_result(r["content"]) for r in messages[-1]["content"]]
        name, args, res = uses[-1]["name"], uses[-1].get("input", {}), results[-1]
        lang = conversation_lang(messages)
        if not isinstance(res, dict):
            res = {"error": str(res)}
        if "rejected" in res:
            return [text(say("rejected", lang, why=res["rejected"]))]
        if "error" in res or "provider_error" in res:
            if name == "book_slot" and "available" in res:
                return [text(say("taken", lang, slots=", ".join(slot_label(s, lang) for s in res["available"])))]
            return [text(say("error", lang, why=res.get("error") or res.get("message")))]
        if name == "book_slot":
            return [tool("create_deposit_order", "o", booking_id=res["booking_id"])]
        if name == "create_deposit_order":
            b = self.state.bookings[args["booking_id"]]
            return [text(say("reserved", lang, slot=slot_label(b["slot"], lang), dep=f"{b['deposit']:.2f}"))]
        if name == "confirm_deposit":
            b = self.state.bookings[args["booking_id"]]
            return [text(say("held", lang, slot=slot_label(b["slot"], lang), dep=f"{b['deposit']:.2f}"))]
        if name == "refresh_hold":
            b = self.state.bookings[args["booking_id"]]
            return [tool("request_capture", "q", booking_id=b["id"], amount=b["deposit"])]
        if name == "list_bookings":
            bs = res["bookings"]
            if not bs:
                return [text(say("no_booking", lang))]
            b = bs[-1]
            status = STATUS_ES.get(b["status"], b["status"]) if lang == "es" else b["status"].replace("_", " ")
            return [text(say("status", lang, id=b["id"], slot=slot_label(b["slot"], lang), status=status))]
        if name.startswith("request_"):
            said = [m["content"] for m in messages if m.get("role") == "user" and isinstance(m.get("content"), str)]
            if said and not RELAY_RE.match(said[-1]):
                # The customer asked to release or give back the deposit: G14's wording.
                return [text((say("sorry", lang) if name == "request_refund" else "") + say("asked_clinic", lang))]
            return [text(say("asked_owner", lang))]
        if name == "execute_mandate":
            req = self.state.mandates[args["mandate_id"]]
            if req["action"] == "capture_deposit":
                return [text(say("captured", lang, amt=f"{req['amount']:.2f}"))]
            if req["action"] == "void_deposit":
                return [text(say("voided", lang))]
            return [text(say("refunded", lang, amt=f"{req['amount']:.2f}"))]
        return [text("Done.")]

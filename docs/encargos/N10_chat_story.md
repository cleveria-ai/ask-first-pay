# N10 — The customer's chat tells the story

Branch `n10-chat-story`, from `main` at the commit that adds this file (N8 is already merged).
Read `docs/encargos/COMMON.md`, `docs/CONTRACT.md`, `docs/JUDGE_PANEL_2026-11.md` and variant V1
with grafts G5 and G14 in `docs/STORY_VARIANTS_2026-11.md` first. Another session works in
parallel on `n9-owner-story` (owner page: `owner.html`, `ledger.html`, `owner.js`, `gate.py`
describe text, the Today panel): do not edit those.

## Goal

In the video (V1, 0:40-2:10) the left half of the screen is the customer's chat. It must read as
a real clinic talking to a real (fictional) person, show that an AI picks PayPal tools, and let
the "too kind to say no" beat happen from a customer's own words.

1. **Fictional LATAM business (V1 change 2).** Business name and currency label come from env
   (`ASK_FIRST_BUSINESS`, default an obviously fictional Latin American clinic name followed by
   "(fictional)" where it appears on screen). Replace hard-coded "Bright Smile Dental" everywhere
   it is shown or sent to the model, including the PayPal `brand_name` from N8.
2. **Real customer names (B8).** Bookings carry the customer's name: taken from the message
   ("I'm Lucía", "soy Lucía", "my name is …") or a name field in the chat, never the constant
   "Customer". The owner card and ledger then show it (N9 reads it through existing data).
3. **Goodwill from a customer message (V1 change 3).** One SYSTEM rule: if a customer explains a
   missed visit and asks for the deposit back, the agent may `request_refund` for the owner to
   decide and must never promise it. The offline scripted model gets a matching rule so the
   keyless demo can play the beat ("my son was in the ER… can I get my deposit back?").
4. **The customer's language (G5).** SYSTEM: reply in the customer's language. The offline model
   understands and answers in Spanish for book, cancel and goodwill ("reservar lunes 9:00",
   "cancelo", "¿me devuelven el depósito?").
5. **Tool-call strip (V1 change 4).** Under each agent reply, a quiet line lists the tools the
   agent called in that turn (`book_slot → create_deposit_order → …`), built from the turn's
   `tool_use` blocks as plain text (no HTML from data; CSP unchanged).
6. **Customer-facing wording (G14).** After the hold: "It is held, not charged. If you cancel, a
   person at the clinic releases it." When asked to release/refund: "I can't move your deposit
   myself; I've asked the clinic." After a void: "Nothing was charged, so there is nothing to
   refund."
7. **Scenario buttons (B10).** The cancellation and goodwill scenarios post as the customer
   (with the customer's name), never as "You".

## Acceptance criteria

| id | says | command |
|---|---|---|
| K1 | the whole suite is green | `.venv/bin/python -m pytest -q` |
| K2 | earlier ladders still pass | `python3 -c "import json,subprocess,sys; sys.exit(any(json.loads(subprocess.run(['python3','scripts/escalera.py','docs/encargos/'+n+'.md','--json'],capture_output=True,text=True).stdout)['d']!=0 for n in ('N1_paypal_adapter','N2_agent','N3_demo','N4_integration','N8_live_ready')))"` |
| K3 | no hard-coded business name remains in code or templates | `! grep -rn "Bright Smile" src/ && .venv/bin/python -m pytest -q -k "business_name"` |
| K4 | bookings carry the customer's name from the message | `.venv/bin/python -m pytest -q -k "customer_name"` |
| K5 | a goodwill message leads to a refund request, never a promise, offline and in the SYSTEM prompt | `.venv/bin/python -m pytest -q -k "goodwill and message"` |
| K6 | the offline model handles Spanish booking, cancellation and goodwill | `.venv/bin/python -m pytest -q -k "spanish"` |
| K7 | the chat shows the turn's tool calls as escaped text | `.venv/bin/python -m pytest -q -k "tool_strip"` |
| K8 | customer-facing wording after hold, ask and void | `.venv/bin/python -m pytest -q -k "customer_wording"` |
| K9 | scenario messages are posted as the customer | `.venv/bin/python -m pytest -q -k "scenario and as_customer"` |
| K10 | the N7 security suite still passes | `.venv/bin/python -m pytest -q tests/security` |
| K11 | no secrets committed | `! git grep -nE "(sk-ant-[A-Za-z0-9_-]{10,}\|(client_secret\|PAYPAL_CLIENT_SECRET)\s*=\s*['\"][A-Za-z0-9_-]{12,})" -- .` |

#!/usr/bin/env python3
"""The demo's own screens against the real PayPal sandbox: three stories, screenshots and a record.

    PAYPAL_CLIENT_ID=... PAYPAL_CLIENT_SECRET=... python scripts/sandbox_ui_run.py
    python scripts/sandbox_ui_run.py --offline --out /tmp/shots --record /tmp/run.md   # rehearsal

Starts the demo on port 8000 (where PayPal sends the buyer back) with the real PayPal adapter,
pairs the owner's phone with the real WebCrypto flow in headless Chromium and plays three
customers through the real pages:

  no-show       book, hold, the owner approves the capture, the agent's replay is refused
  cancellation  book, hold, the owner approves the void: nothing charged
  goodwill      book, hold, capture after a no-show, then the owner approves a partial refund

For each booking it prints `APPROVE <customer> <PayPal link>` and waits: a sandbox buyer opens the
link in a browser and approves; PayPal sends that browser back to /chat/return, which holds the
deposit. Then it goes on by itself. It saves PNGs named 12-sandbox-*.png and appends a record to
docs/SANDBOX_UI_RUN.md: the ledger rows with PayPal's ids and every HTTP call's method, path and
status. Never tokens, headers or credentials. The agent model is the offline scripted one (no
Anthropic key is read); the screens say so.

Needs playwright (`pip install playwright`, not a project dependency).
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "libs" / "ask-first-mandate" / "src")]

from sandbox_run import Recorder, now  # noqa: E402

DESKTOP = {"width": 1280, "height": 720}
PHONE = {"width": 375, "height": 812}
CHROMIUM = os.environ.get("ASK_FIRST_CHROMIUM", "/opt/pw-browsers/chromium")
STORIES = [("no_show", "Lucía", 0), ("cancel", "Mateo", 1), ("goodwill", "Sofía", 2)]
HEADER = """# PayPal sandbox runs through the demo's screens

Appended by `scripts/sandbox_ui_run.py`. Each run played three customers through the real pages
(chat, PayPal's own approval page, the owner's phone, the ledger) against the PayPal sandbox. It
lists the ledger rows with the ids PayPal returned and every HTTP call's method, path and status
(never tokens, headers or credentials). Screenshots: `docs/screenshots/12-sandbox-*.png`.

A `reauthorize` answered 422 is expected: before a no-show capture the agent asks PayPal to refresh
the hold, PayPal declines for a fresh one, and the agent goes on with the hold it has
(`refresh_hold` in `src/ask_first_pay/agent/tools.py`).
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    ap.add_argument("--record", default=str(ROOT / "docs" / "SANDBOX_UI_RUN.md"))
    ap.add_argument("--offline", action="store_true", help="rehearse against the simulated PayPal")
    ap.add_argument("--wait", type=int, default=900, help="seconds to wait for each buyer approval")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    os.environ.pop("ANTHROPIC_API_KEY", None)           # the scripted model: nothing is sent to a model API
    os.environ.pop("ASK_FIRST_DB", None)
    os.environ.setdefault("ASK_FIRST_TZ", "America/Mexico_City")
    recorder = Recorder()
    if args.offline:
        os.environ.pop("PAYPAL_CLIENT_ID", None)
        provider = None
    else:
        if not (os.environ.get("PAYPAL_CLIENT_ID") and os.environ.get("PAYPAL_CLIENT_SECRET")):
            print("Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (sandbox) in the environment.")
            return 2
        from ask_first_pay.paypal import PayPalProvider
        provider = PayPalProvider(transport=recorder)   # sandbox only; credentials from the environment

    import uvicorn
    from playwright.sync_api import sync_playwright

    from ask_first_pay.demo import create_app
    from ask_first_pay.demo.front import SLOT_LABELS

    app = create_app(provider=provider)
    demo = app.state.demo
    if demo.simulated != args.offline:
        print("The demo did not start with the expected provider.")
        return 2
    code = demo.new_pairing_code()
    port = int(os.environ.get("PORT", "8000"))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    started = now()
    held_ids: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM if Path(CHROMIUM).exists() else None)
        page = browser.new_context(viewport=DESKTOP, device_scale_factor=1).new_page()

        def go(path: str):
            page.goto(base + path)
            page.wait_for_load_state("networkidle")

        def shot(name: str, size=DESKTOP, scroll_to: str | None = None):
            if size != page.viewport_size:
                page.set_viewport_size(size)
                page.reload()
                page.wait_for_load_state("networkidle")
            if scroll_to:
                page.evaluate("s => document.querySelector(s).scrollIntoView({block: 'start'})", scroll_to)
            page.wait_for_timeout(350)
            page.screenshot(path=str(out / name))
            print(f"  saved {out / name}", flush=True)
            if size != DESKTOP:
                page.set_viewport_size(DESKTOP)

        def approve_first():
            go("/owner")
            waiting = {m["id"] for m in demo.mandate_rows() if m["state"] == "pending"}
            page.locator(".mandate").first.locator(".approve").click()
            # The page reloads itself when the pending list changes, so its "Approved" line can be
            # gone before we look: ask the server instead. "used" = the gate executed it at PayPal.
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                states = {m["id"]: m["state"] for m in demo.mandate_rows()}
                if waiting and all(states.get(i) == "used" for i in waiting):
                    break
                time.sleep(0.5)
            else:
                raise TimeoutError(f"the approved mandate was not executed: {[states.get(i) for i in waiting]}")
            page.wait_for_timeout(1500)
            page.wait_for_load_state("networkidle")

        def book_and_hold(name: str, slot: str) -> dict:
            if held_ids:                                  # each customer in their own conversation
                with demo.lock:
                    demo.front.new_conversation()
            go("/chat")
            page.fill("#message", f"Hi, I'm {name}, please book {slot}")
            page.get_by_role("button", name="Send", exact=True).click()
            page.wait_for_load_state("networkidle")
            link = page.get_by_role("link", name="Hold the deposit").last
            if args.offline:
                link.click()
                page.get_by_role("button", name="Approve the hold").click()
                page.wait_for_load_state("networkidle")
            else:
                print(f"APPROVE {name} {link.get_attribute('href')}", flush=True)
            deadline = time.monotonic() + args.wait
            while time.monotonic() < deadline:
                found = demo.front.latest("deposit_held")
                if found is not None and found[1]["order_id"] not in held_ids:
                    held_ids.add(found[1]["order_id"])       # booking ids restart in each conversation
                    print(f"HELD {name} order {found[1]['order_id']}", flush=True)
                    return found[1]
                time.sleep(1)
            raise TimeoutError(f"the buyer did not approve {name}'s deposit in {args.wait} s")

        def scenario(button: str):
            go("/chat")
            page.get_by_role("button", name=button).click()
            page.wait_for_load_state("networkidle")

        go("/owner")                                       # pair the phone
        page.fill("#code", code)
        page.click("#pair-form button")
        page.wait_for_selector("#device-status[data-paired=yes]", timeout=10_000)

        # 1. no-show: hold, the owner signs the capture, the replay is refused
        book_and_hold(STORIES[0][1], SLOT_LABELS[STORIES[0][2]])
        go("/chat")
        shot("12-sandbox-chat-held.png")
        scenario("No-show")
        go("/owner")
        shot("12-sandbox-owner-approval.png")
        shot("12-sandbox-owner-mobile.png", PHONE)
        approve_first()
        go("/ledger")
        page.get_by_role("button", name="Agent tries to replay the last mandate").click()
        page.wait_for_load_state("networkidle")
        page.locator(".ag-cell", has_text="replay").first.wait_for(timeout=10_000)
        page.locator("#ledger-detail").wait_for(state="visible", timeout=10_000)
        shot("12-sandbox-ledger-replay.png")

        # 2. cancellation: hold, the owner signs the void, nothing charged
        book_and_hold(STORIES[1][1], SLOT_LABELS[STORIES[1][2]])
        scenario("Cancellation")
        approve_first()
        go("/chat")
        shot("12-sandbox-cancellation-voided.png")

        # 3. goodwill: capture after a no-show, then the owner gives part back
        book_and_hold(STORIES[2][1], SLOT_LABELS[STORIES[2][2]])
        scenario("Goodwill")
        approve_first()                                   # the capture
        approve_first()                                   # the refund
        go("/ledger")
        shot("12-sandbox-ledger.png")
        go("/owner")
        shot("12-sandbox-today-mobile.png", PHONE, scroll_to="#today")
        browser.close()

    rows, check = demo.ledger_rows()
    write_record(Path(args.record), started, rows, check, recorder.calls, args.offline)
    server.should_exit = True
    print(f"Run record appended to {args.record}", flush=True)
    bad = [r for r in rows if r["result"] not in ("executed", "rejected")]
    return 0 if check.get("ok") and not bad else 1


def write_record(path: Path, started: str, rows: list[dict], check: dict, calls, offline: bool) -> None:
    where = "simulated PayPal, rehearsal" if offline else "sandbox"
    lines = [f"\n## Run {started} ({where})\n",
             f"Finished {now()}. Agent model: offline scripted. Ledger chain check: "
             f"{'intact' if check.get('ok') else 'BROKEN'}.\n",
             "| n | result | action | PayPal resource | amount | PayPal answered | PayPal-Request-Id (mandate id) |",
             "|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["n"]):
        result = r["result"] + (f" · {r['reason']}" if r["reason"] else "")
        cells = [str(r["n"]), result, r["action"], r["resource"], r["amount_text"], r["paypal_id"], r["request_id"]]
        lines.append("| " + " | ".join(str(c).replace("|", "/") for c in cells) + " |")
    lines += ["", "HTTP calls (method, path, status):", ""]
    lines += [f"- `{m} {p}` {s}" for m, p, s in calls]
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", encoding="utf-8") as f:
        if new:
            f.write(HEADER)
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())

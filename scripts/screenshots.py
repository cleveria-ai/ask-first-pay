"""Devpost screenshots of the offline demo, taken in headless Chromium.

    .venv/bin/pip install playwright        # in your environment only; not a project dependency
    .venv/bin/python scripts/screenshots.py [--out docs/screenshots]

Starts the demo in-process exactly as scripts/demo.sh does (no keys), pairs a phone with the
real WebCrypto flow, plays the stories by pressing the real buttons and saves PNGs at 1280x720
(desktop) and 375x812 (phone):

  01-chat-booking.png        the customer books and the deposit is held
  02-owner-approval.png      the owner's phone shows the signed capture mandate
  03-ledger-replay.png       the replay is rejected on the ledger, row detail open
  04-cancellation-voided.png a cancellation is approved and the hold voided
  05-owner-mobile.png        the owner's view at 375 px
  06-ledger-mobile.png       the ledger at 375 px
  07-chat-mobile.png         the chat at 375 px
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_demo import CHROMIUM, ROOT, start_local_demo  # noqa: E402

DESKTOP = {"width": 1280, "height": 720}
PHONE = {"width": 375, "height": 812}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    ap.add_argument("--dark", action="store_true", help="also take the desktop shots in dark mode")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    base, code, server = start_local_demo()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM if Path(CHROMIUM).exists() else None)
        ctx = browser.new_context(viewport=DESKTOP, device_scale_factor=1)
        page = ctx.new_page()

        def shot(name: str, size=DESKTOP, scroll_to: str | None = None):
            if size != page.viewport_size:
                page.set_viewport_size(size)
                page.reload()                       # the grids pick their columns at load
                page.wait_for_load_state("networkidle")
            if scroll_to:
                page.evaluate("s => document.querySelector(s).scrollIntoView({block: 'start'})", scroll_to)
            page.wait_for_timeout(350)
            path = out / name
            page.screenshot(path=str(path))
            print(f"  saved {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")

        def go(path: str):
            page.goto(base + path)
            page.wait_for_load_state("networkidle")

        def approve_first():
            go("/owner")
            card = page.locator(".mandate").first
            card.locator(".approve").click()
            card.locator(".result").filter(has_text="Approved").wait_for(timeout=10_000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(900)

        # pair the phone (same browser context = same IndexedDB key)
        go("/owner")
        page.fill("#code", code)
        page.click("#pair-form button")
        page.wait_for_selector("#device-status[data-paired=yes]", timeout=10_000)

        # 1. booking: type, hold, approve on the simulated checkout
        go("/chat")
        page.fill("#message", "book Mon 16 Nov 09:00")
        page.get_by_role("button", name="Send", exact=True).click()
        page.wait_for_load_state("networkidle")
        page.get_by_role("link", name="Hold the deposit").last.click()
        page.get_by_role("button", name="Approve the hold").click()
        page.wait_for_load_state("networkidle")
        shot("01-chat-booking.png")
        shot("07-chat-mobile.png", PHONE)

        # 2. no-show: the agent asks; the owner's phone shows the signed fields
        go("/chat")
        page.get_by_role("button", name="No-show").click()
        page.wait_for_load_state("networkidle")
        shot("02-owner-approval.png")
        shot("05-owner-mobile.png", PHONE)
        page.set_viewport_size(DESKTOP)
        approve_first()

        # 3. replay on the ledger: rejected, detail of the newest row open (#latest)
        go("/ledger")
        page.get_by_role("button", name="Agent tries to replay the last mandate").click()
        page.wait_for_load_state("networkidle")
        page.locator(".ag-cell", has_text="replay").first.wait_for(timeout=10_000)
        page.locator("#ledger-detail").wait_for(state="visible", timeout=10_000)
        shot("03-ledger-replay.png")
        shot("06-ledger-mobile.png", PHONE, scroll_to="[data-toolbar=ledger]")
        page.set_viewport_size(DESKTOP)

        # 4. cancellation: void approved, nothing charged
        go("/chat")
        page.get_by_role("button", name="Cancellation").click()
        page.wait_for_load_state("networkidle")
        approve_first()
        go("/chat")
        shot("04-cancellation-voided.png")

        if args.dark:
            dctx = browser.new_context(viewport=DESKTOP, color_scheme="dark")
            page = dctx.new_page()
            go("/ledger#n=2")
            shot("08-ledger-dark.png")
        browser.close()
    server.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""N9 in a real browser (headless Chromium through Playwright, the optional `browser` extra):
on a 375x812 phone the first Approve button is visible without scrolling, a tap still signs
with WebCrypto, and a new request makes the phone buzz and badges the tab title.

Skipped, with the reason, when Playwright or its Chromium is missing
(`pip install -e ".[dev,browser]" && python -m playwright install chromium`)."""
import socket
import threading
import time

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="Playwright not installed (optional extra: browser)")

PHONE = {"width": 375, "height": 812}
# A stand-in for the phone's motor: counts navigator.vibrate calls across reloads.
BUZZ_SPY = """
Object.defineProperty(navigator, 'vibrate', {configurable: true, value: function (p) {
  var n = Number(sessionStorage.getItem('buzzes') || 0) + 1;
  sessionStorage.setItem('buzzes', String(n));
  return true;
}});
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live(tmp_path, monkeypatch):
    for k in ("ASK_FIRST_MANDATE_TTL_MIN", "ASK_FIRST_VIDEO", "ASK_FIRST_DB", "ANTHROPIC_API_KEY", "PAYPAL_CLIENT_ID"):
        monkeypatch.delenv(k, raising=False)
    import uvicorn

    from ask_first_pay.demo import create_app
    from ask_first_pay.fake_provider import FakeProvider
    app = create_app(FakeProvider(), str(tmp_path / "ledger.jsonl"))
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.02)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:                       # noqa: BLE001 - no Chromium downloaded
            server.should_exit = True
            pytest.skip(f"Chromium for Playwright is not installed: {str(e).splitlines()[0]}")
        yield {"base": f"http://127.0.0.1:{port}", "state": app.state.demo, "browser": browser}
        browser.close()
    server.should_exit = True


def _paired_phone(live):
    ctx = live["browser"].new_context(viewport=PHONE, device_scale_factor=1, is_mobile=True, has_touch=True)
    ctx.add_init_script(BUZZ_SPY)
    page = ctx.new_page()
    page.goto(live["base"] + "/owner")
    page.fill("#code", live["state"].new_pairing_code())
    page.click("#pair-form button")
    page.wait_for_selector("#device-status[data-paired=yes]", timeout=10_000)
    return page


def _until(check, timeout=10.0):
    """Poll from Python: the page's CSP (script-src 'self') forbids Playwright's string predicates."""
    end = time.time() + timeout
    while time.time() < end:
        if check():
            return True
        time.sleep(0.1)
    raise AssertionError("condition not met in time")


def _approve_fully_visible(page) -> dict:
    page.wait_for_selector(".mandate .approve")
    page.wait_for_selector("[data-grid].js-grid")               # the page is fully built (AG Grid ran)
    page.wait_for_load_state("networkidle")
    box = page.locator(".mandate .approve").first.bounding_box()
    return {"box": box, "scroll_y": page.evaluate("window.scrollY"),
            "scroll_w": page.evaluate("document.documentElement.scrollWidth"),
            "wide": page.evaluate("() => [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > 376 && !e.closest('.grid-wrap')).slice(0, 8).map(e => e.tagName + '.' + e.className + ' ' + Math.round(e.getBoundingClientRect().right))")}


def test_approve_above_fold_on_a_375x812_phone_for_capture_and_void(live):
    page = _paired_phone(live)
    for scenario, words in (("no_show", "Keep up to $10.00"), ("cancel", "Moves $0.00")):
        page.request.post(live["base"] + f"/scenario/{scenario}")
        page.goto(live["base"] + "/owner")
        assert words in page.locator(".mandate .headline").first.inner_text()
        got = _approve_fully_visible(page)
        b = got["box"]
        assert got["scroll_y"] == 0 and got["scroll_w"] <= PHONE["width"], got     # no scrolling either way
        assert b["y"] >= 0 and b["y"] + b["height"] <= PHONE["height"], (scenario, b)
        assert b["x"] >= 0 and b["x"] + b["width"] <= PHONE["width"], (scenario, b)
        assert b["height"] >= 44                                                 # a thumb-sized target
        # and the tap still signs in this browser with the non-extractable WebCrypto key
        card = page.locator(".mandate").first
        card.locator(".approve").click()
        card.locator(".result").filter(has_text="Approved").wait_for(timeout=10_000)
    assert [e["result"] for e in live["state"].agent.view_ledger()["entries"]] == ["executed", "executed"]


def test_owner_page_buzzes_and_badges_the_title_on_a_new_request(live):
    page = _paired_phone(live)
    page.goto(live["base"] + "/owner")
    title = page.title()
    assert not title.startswith("(") and page.locator(".mandate").count() == 0
    page.wait_for_timeout(3500)                                   # one poll with nothing new: no buzz
    assert page.evaluate("sessionStorage.getItem('buzzes')") is None and page.title() == title

    page.request.post(live["base"] + "/scenario/no_show")         # the agent asks, from elsewhere
    _until(lambda: page.title().startswith("(1) "))
    page.wait_for_selector(".mandate .approve", timeout=10_000)   # the card came in without a tap
    assert page.evaluate("sessionStorage.getItem('buzzes')") == "1"
    assert page.title() == "(1) " + title

    # while the owner is reading a card, a second request never pulls the page away
    page.locator(".mandate details summary").first.click()        # a tap clears the badge
    assert page.title() == title
    page.request.post(live["base"] + "/scenario/cancel")
    page.wait_for_selector("#new-request:not([hidden])", timeout=10_000)
    assert page.locator("#new-request").inner_text() == "A new request arrived · show it"
    assert page.title() == "(1) " + title and page.locator(".mandate").count() == 1
    assert page.evaluate("sessionStorage.getItem('buzzes')") == "2"
    page.locator("#new-request").click()
    _until(lambda: page.locator(".mandate").count() == 2)


def test_ledger_detail_shows_the_request_id_and_the_paypal_id_in_the_browser(live):
    page = _paired_phone(live)
    page.set_viewport_size({"width": 1280, "height": 720})
    page.request.post(live["base"] + "/scenario/no_show")
    page.goto(live["base"] + "/owner")
    card = page.locator(".mandate").first
    jti = card.get_attribute("data-id")
    card.locator(".approve").click()
    card.locator(".result").filter(has_text="Approved").wait_for(timeout=10_000)
    capture_id = next(iter(live["state"].provider.captures))
    page.goto(live["base"] + "/ledger")
    detail = page.locator("#ledger-detail")
    detail.wait_for(state="visible", timeout=10_000)              # the newest row opens by itself
    text = detail.inner_text()
    assert f"PayPal-Request-Id: {jti}" in text and f"PayPal capture id {capture_id} (COMPLETED)" in text
    dd = detail.locator("dd").nth(2).bounding_box()               # the value column stays readable
    assert dd["width"] >= 200, dd

import os

import pytest

from ask_first_pay.paypal import PayPalProvider


@pytest.mark.live
@pytest.mark.skipif(not (os.environ.get("PAYPAL_CLIENT_ID") and os.environ.get("PAYPAL_CLIENT_SECRET")),
                    reason="needs PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (sandbox)")
def test_live_create_order_prints_payer_link():
    """Creates a USD 10.00 AUTHORIZE order in the PayPal sandbox and prints the payer link.

    Run: PAYPAL_CLIENT_ID=... PAYPAL_CLIENT_SECRET=... .venv/bin/python -m pytest -q -m live -s tests/paypal
    Manual steps (a browser is needed to approve):
      1. Open the printed link and log in with a sandbox *personal* (buyer) account.
      2. Approve the payment; PayPal redirects away (the redirect target does not matter).
      3. In a Python shell: p = PayPalProvider(); a = p.authorize("<order id>");
         then p.capture(a.authorization_id, 10.0, "manual-1") or p.void(a.authorization_id, "manual-2").
    """
    p = PayPalProvider()
    o = p.create_order(10.0, "USD", "live-smoke-1")
    print(f"\nORDER {o.order_id} status={o.status}\nPAYER LINK: {o.approve_url}")
    assert o.order_id and o.approve_url.startswith("https://")

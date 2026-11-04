def test_pages_answer_200_and_show_their_key_content(demo):
    c = demo.client
    chat = c.get("/chat")
    assert chat.status_code == 200
    assert 'name="message"' in chat.text and '<label for="message">' in chat.text

    demo.client.post("/scenario/no_show")
    owner = c.get("/owner")
    assert owner.status_code == 200
    assert 'id="pending-list"' in owner.text and "capture_deposit" in owner.text
    assert "Approve" in owner.text and "Decline" in owner.text
    assert "single use" in owner.text.lower() or "Single use" in owner.text

    ledger = c.get("/ledger")
    assert ledger.status_code == 200
    assert "Chain check" in ledger.text


def test_pages_chain_check_turns_intact_after_an_attempt(demo):
    demo.client.post("/scenario/cancel")
    (jti,) = demo.pending_ids()
    assert demo.approve(jti).status_code == 200
    text = demo.client.get("/ledger").text
    assert "Chain check:" in text and "intact" in text and "1 of 1" in text


def test_pages_owner_shows_signed_fields_not_model_text(demo):
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    text = demo.client.get("/owner").text
    assert demo.state.agent.describe(jti) in text.replace("&#39;", "'")
    assert "AUTH-" in text and "10.00" in text


def test_pages_have_no_cdn_and_serve_vendored_grid(demo):
    for path in ("/", "/chat", "/owner", "/ledger"):
        html = demo.client.get(path).text
        assert "http://" not in html and "https://" not in html
    js = demo.client.get("/static/vendor/ag-grid-community.min.js")
    assert js.status_code == 200 and len(js.content) > 100_000
    assert demo.client.get("/static/vendor/AG-GRID-LICENSE.txt").status_code == 200


def test_pages_chat_books_and_confirms_after_the_fake_checkout(demo):
    r = demo.client.post("/chat/send", data={"message": "book Tue 15:00"})
    assert r.status_code == 303
    assert "/checkout/ORDER-0001" in demo.client.get("/chat").text
    assert demo.client.get("/checkout/ORDER-0001").status_code == 200
    demo.client.post("/checkout/ORDER-0001/approve")
    assert "Confirmed: Tue 17 Nov 15:00" in demo.client.get("/chat").text
    assert demo.calls("capture") == [] and demo.calls("void") == []   # the booking only holds money


def test_pages_unpaired_phone_cannot_approve(tmp_path):
    from tests.demo.conftest import Demo
    d = Demo(tmp_path)                       # never paired
    d.client.post("/scenario/no_show")
    (jti,) = d.pending_ids()
    assert d.approve(jti).status_code == 400
    assert d.calls("capture") == []


def test_pages_pairing_code_is_single_use(tmp_path):
    from ask_first import generate_pair, public_key_hex

    from tests.demo.conftest import Demo
    d = Demo(tmp_path)
    code = d.state.new_pairing_code()
    body = {"code": code, "public_key": public_key_hex(d.pub)}
    assert d.client.post("/owner/pair", json=body).status_code == 200
    again = {"code": code, "public_key": public_key_hex(generate_pair()[1])}
    assert d.client.post("/owner/pair", json=again).status_code == 400


def test_pages_browser_signs_the_canonical_bytes_the_server_serves(demo):
    demo.client.post("/scenario/cancel")
    (m,) = [x for x in demo.client.get("/owner/api/mandates").json()["mandates"] if x["state"] == "pending"]
    sig = demo.priv.sign(m["canonical"].encode("utf-8")).hex()       # what WebCrypto signs
    r = demo.client.post("/owner/approve", json={"mandate_id": m["id"], "signature": sig})
    assert r.status_code == 200

def test_no_show_captures_exactly_once_and_only_after_approval(demo):
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    assert demo.calls("capture") == []                 # asked, not done
    assert demo.provider.captures == {}
    assert demo.approve(jti).status_code == 200
    caps = demo.calls("capture")
    assert len(caps) == 1 and caps[0][2] == 10.0 and caps[0][3] == jti   # request_id = mandate jti
    assert demo.calls("refund") == [] and demo.calls("void") == []
    # approving again, or replaying, never captures twice
    demo.client.post("/replay")
    assert len(demo.calls("capture")) == 1
    assert "Done: $10.00 captured" in demo.client.get("/chat").text


def test_no_show_wrong_signature_does_not_capture(demo):
    from ask_first import generate_pair, sign_envelope
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    forged = sign_envelope(generate_pair()[0], demo.state.owner.pending[jti])
    r = demo.client.post("/owner/approve", json={"mandate_id": jti, "signature": forged})
    assert r.status_code == 400 and demo.calls("capture") == []


def test_cancel_voids_and_never_refunds(demo):
    demo.client.post("/scenario/cancel")
    (jti,) = demo.pending_ids()
    assert demo.calls("void") == []
    assert demo.approve(jti).status_code == 200
    voids = demo.calls("void")
    assert len(voids) == 1 and voids[0][2] == jti
    assert demo.calls("refund") == [] and demo.calls("capture") == []
    assert list(demo.provider.auths.values())[0].status == "VOIDED"
    assert "nothing needs refunding" in demo.client.get("/chat").text


def test_cancel_through_the_chat_asks_the_owner_to_void(demo):
    demo.client.post("/chat/send", data={"message": "book Wed 10:00"})
    demo.client.post("/checkout/ORDER-0001/approve")
    demo.client.post("/chat/send", data={"message": "please cancel"})
    (jti,) = demo.pending_ids()
    assert "void_deposit" in demo.state.agent.describe(jti)
    assert demo.calls("void") == []


def test_goodwill_captures_then_refunds_with_two_approvals(demo):
    demo.client.post("/scenario/goodwill")
    (cap,) = demo.pending_ids()
    demo.approve(cap)
    (ref,) = demo.pending_ids()
    assert ref != cap and "refund_deposit" in demo.state.agent.describe(ref)
    assert demo.calls("refund") == []
    demo.approve(ref)
    assert len(demo.calls("capture")) == 1 and len(demo.calls("refund")) == 1
    assert demo.calls("refund")[0][2] == 4.0 and demo.calls("refund")[0][3] == ref


def test_rejected_declined_mandate_shows_on_the_ledger_page(demo):
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    assert demo.decline(jti).status_code == 200
    assert demo.calls("capture") == []
    page = demo.client.get("/ledger").text
    assert "rejected" in page and "not_approved" in page
    assert "intact" in page
    assert demo.pending_ids() == []                      # it left the owner's queue


def test_rejected_replayed_mandate_shows_on_the_ledger_page(demo):
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    demo.approve(jti)
    demo.client.post("/replay")
    page = demo.client.get("/ledger").text
    assert "executed" in page and "rejected" in page and "replay" in page
    assert len(demo.calls("capture")) == 1


def test_rejected_decline_of_unknown_mandate_is_refused(demo):
    assert demo.decline("nope").status_code == 400

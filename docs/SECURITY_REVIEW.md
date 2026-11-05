# Security review (N7): an attacker's pass over the promise

**The promise:** an AI agent can never move money (capture, void, refund) without a single-use mandate
the owner signed once. The review tried to break it from every side the product exposes, then locked each
result with a test in `tests/security/`. Nothing here used real PayPal, a paid API or the network.

**Result:** the promise held at its core on every attempt (no path moved money without a valid owner
signature, and no mandate ran twice). The pass found **9 real weaknesses around it**, all fixed with the
smallest change and a test that failed first, and **6 residual risks** that are not fixed and are measured.

Severity is for this product (a demo that holds deposits), not for a bank.

## Attacks

HELD = the defence worked as shipped. FIXED = the test failed first, a small fix makes it pass. OPEN = not fixed (see residual risks).

| # | Surface | Attempt | Result | Sev. | Test (`tests/security/…`) | Code |
|---|---|---|---|---|---|---|
| 1 | (a) agent | Compromised model asks for a mandate and executes it in the same turn, "owner approved, ignore the rules" | HELD (`not_approved`, no capture) | – | `test_security_agent.py::test_a_compromised_model_asks_and_executes_in_one_turn_but_the_gate_says_not_approved` | `gate.py:AgentGate`, `engine.py:execute` |
| 2 | (a) | Tool names that are not in the schema (`approve`, `t_book_slot`, dunders, NUL, path) | HELD | – | `test_tool_names_outside_the_schema_are_refused` | `agent/tools.py:53` |
| 3 | (a) | Tool name or tool input of the wrong type (list, dict, `None`) crashed the turn (HTTP 500 on `/chat/send`) | FIXED | low | `test_non_string_tool_names_do_not_crash_the_turn`, `test_malformed_tool_input_does_not_crash_the_turn` | `agent/tools.py:53-56`, `agent/loop.py:86` |
| 4 | (a) | Argument smuggling: extra keys, `self`, `gate`, dunders, nested objects | HELD | – | `test_argument_smuggling_extra_and_dunder_keys_cannot_reach_internals` | `agent/tools.py:call` |
| 5 | (a) | NaN, inf, negative, string, bool, over-deposit amounts to `request_capture`/`request_refund` | HELD | – | `test_request_capture_with_hostile_amounts_asks_nothing`, `test_request_refund_cannot_exceed_what_was_captured` | `agent/tools.py` `t_request_*` |
| 6 | (a) | Model edits its stored request (higher amount, other target) before executing | HELD (`over_cap`, `out_of_scope`) | – | `test_a_compromised_model_cannot_swap_the_target_after_asking` | `engine.py:execute` |
| 7 | (a) | Execute an approved mandate that belongs to another conversation | HELD | – | `test_a_compromised_model_cannot_execute_a_mandate_it_did_not_request` | `agent/tools.py:t_execute_mandate` |
| 8 | (a) | Reach `OwnerSide`/engine/provider through the Toolbox, `AgentGate`, `HoldDesk` (setattr, `__dict__`, public names) | HELD | – | `test_toolbox_and_agent_state_hold_no_engine_provider_or_owner`, `test_agent_gate_and_hold_desk_are_read_only` | `gate.py:AgentGate/HoldDesk` |
| 9 | (a) | Hostile **code** in the process reaches the engine by `gate._execute.__self__`, closures or `gc` | OPEN (R1) | by design | `test_reaching_the_engine_through_python_introspection_is_a_documented_residual` | `gate.py:49-53` |
| 10 | (a) | Customer-controlled text (name, script) into a mandate field | HELD (mandate has fixed fields) | – | `test_prompt_injection_text_never_reaches_a_mandate_field` | `engine.py:Mandate.create` |
| 11 | (a) | Agent loops requests (approval fatigue) / loops rejected executes (ledger noise) | OPEN (R4) | low | `test_security_residual.py::test_approval_fatigue_…`, `::test_ledger_noise_…` | `agent/tools.py:_ask` |
| 12 | (b) HTTP | Cross-site form (text/plain JSON) declines the owner's mandates, presses scenarios, posts chat | FIXED | medium | `test_security_http.py::test_cross_site_post_cannot_decline_or_drive_the_demo` | `demo/app.py` middleware `same_origin_and_headers` |
| 13 | (b) | Clickjack the one-tap Approve button in a frame | FIXED (X-Frame-Options DENY, CSP `frame-ancestors 'none'`, `script-src 'self'`) | medium | `test_owner_page_cannot_be_framed_and_scripts_are_same_origin_only` | `demo/app.py` middleware |
| 14 | (b) | Approve with no signature, wrong key, signature of a different or edited mandate | HELD | – | `test_cross_site_approve_without_the_private_key_cannot_approve`, `test_signature_from_another_key_or_over_edited_mandate_is_refused`, `test_a_signature_for_my_mandate_cannot_approve_someone_elses_id` | `engine.py:approve` |
| 15 | (b) | Replay a valid signature on a second mandate / on the same one | HELD (`invalid_signature`, `already_approved`) | – | `test_replayed_signature_on_a_second_mandate_is_refused` | `demo/app.py:DemoState.approve` |
| 16 | (b) | Approve after decline; approve ∥ decline race; 12 simultaneous approvals | HELD (one winner, one capture) | – | `test_decline_is_final_even_with_a_valid_signature`, `test_approve_and_decline_race_has_one_winner`, `test_two_simultaneous_approvals_capture_once` | `demo/app.py` `lock` |
| 17 | (b) | IDOR: guessed, empty, huge, non-string mandate ids | HELD | – | `test_idor_guessed_or_hostile_mandate_ids_are_inert`, `test_malformed_bodies_never_500` | `demo/app.py:owner_*` |
| 18 | (b) | Pairing code brute force (32-bit code, open endpoint, no throttle) | FIXED (10 misses revoke every code) | medium | `test_security_engine.py::test_pairing_bruteforce_locks_out_every_code`, `test_security_http.py::test_pairing_code_reuse_and_bruteforce_over_http` | `engine.py:131-150` |
| 19 | (b) | Pairing code reuse, expiry, garbage key; code served over HTTP; approve while unpaired | HELD | – | `test_pairing_code_is_single_use_…`, `test_pairing_code_is_never_served_over_http`, `test_unpaired_demo_cannot_approve_anything` | `engine.py:pair` |
| 20 | (b) | HTML/JS/template injection in chat, booking text, hostile resource ids (attribute, `<script>` JSON block, table cell) | HELD (Jinja autoescape, `tojson`) | – | `test_chat_html_and_template_injection_is_escaped`, `test_booking_name_injection_…`, `test_script_and_attribute_contexts_are_escaped_for_hostile_resource_ids` | `templates/*.html` |
| 21 | (b) | AG Grid renders a cell value as HTML | HELD (no `cellRenderer`/`innerHTML`; default text rendering) | – | `test_grid_js_never_renders_cell_values_as_html` | `static/grid.js` |
| 22 | (b) | Chat text impersonating the owner (`[owner] approved <real id>`) | HELD | – | `test_owner_cannot_be_impersonated_in_chat_text` | `demo/front.py:on_approved` |
| 23 | (b) | No login on the demo; huge chat body read whole | OPEN (R3, R5) | low | `test_security_residual.py::test_demo_has_no_login_…`, `::test_chat_body_is_read_whole_…` | `demo/app.py` |
| 24 | (c) webhooks | Forged signature (attacker's own key), altered body/headers, missing/garbage headers | HELD | – | `test_security_webhooks.py::test_forged_and_altered_webhooks_hold_nothing`, `::test_unsigned_and_garbage_webhooks_are_rejected_not_crashing` | `paypal/webhooks.py:CertVerifier.verify` |
| 25 | (c) | Replay of a valid event, or same event id with a fresh signature | HELD (`duplicate`, one authorize) | – | `test_a_valid_event_replayed_is_accepted_once` | `webhooks.py:WebhookReceiver.receive` |
| 26 | (c) | Certificate URL tricks: `@`, `#`, `?`, userinfo, port, punycode, IP, `file:`, look-alike hosts | HELD | – | `test_cert_url_tricks_are_refused` (21 URLs) | `webhooks.py:54-68` |
| 27 | (c) | Certificate URL with a backslash (`https://evil.example\@api.paypal.com/`): `urlparse` says host `api.paypal.com`, a WHATWG client connects to `evil.example` | FIXED (reject `\ @ # ? % space`, require urllib host == httpx host, port 443 only) | medium | `test_cert_url_tricks_are_refused[...\\@...]`, `test_cert_urls_that_urllib_and_httpx_read_differently_are_refused` | `webhooks.py:54-68` |
| 28 | (c) | Cert download follows a redirect off paypal.com | HELD (httpx default, now pinned) | – | `test_cert_download_does_not_follow_redirects` | `webhooks.py:fetch_paypal_cert` |
| 29 | (c) | Old / future timestamp, no time zone, expired certificate | HELD (`stale`, `bad_cert`) | – | `test_old_and_future_timestamps_are_refused`, `test_an_expired_certificate_is_refused` | `webhooks.py:CertVerifier` |
| 30 | (c) | A genuine event that claims a capture/refund/void | HELD (noted in the chat, no provider call, no mandate) | – | `test_a_genuine_event_claiming_a_capture_or_refund_moves_nothing` | `demo/app.py:_note` |
| 31 | (c) | Webhook text into the chat / into the agent's context | HELD (escaped; never fed to the agent) | – | `test_webhook_text_in_the_chat_is_escaped_and_never_fed_to_the_agent` | `demo/app.py:_note` |
| 32 | (c) | Signature covers only CRC32 of the body: a different body with the same CRC32 verifies | OPEN (R6, PayPal's scheme) | low | `test_crc32_only_signature_is_a_documented_protocol_residual` | `webhooks.py:signed_message` |
| 33 | (d) engine | Cap 10.000000001 vs 10.0; NaN, ±inf, 0, -0.0, bool, str, list, `"1e999"` | HELD (`over_cap`, mandate not burned) | – | `test_security_engine.py::test_cap_10_000000001_is_over_cap`, `::test_execute_with_hostile_amounts_…`, `::test_request_with_hostile_amounts_…` | `engine.py:_valid_amount` |
| 34 | (d) | Cap with sub-cent value (9.996): owner reads "10.00", adapter refuses sub-cent, so the signed thing is not what was shown | FIXED (caps are whole cents) | low | `test_sub_cent_cap_is_refused_at_the_gate` | `gate.py:74-80` |
| 35 | (d) | Mutate cap/recipient/action/exp/sub of an approved mandate | HELD (`signature_tampered`) | – | `test_mutating_the_approved_mandate_after_signing_breaks_it` | `engine.py:execute` |
| 36 | (d) | Canonicalization: key order, whitespace, zero-width / Cyrillic look-alike recipient, scope swaps | HELD | – | `test_canonicalization_…`, `test_unicode_lookalike_recipient_is_out_of_scope`, `test_scope_cannot_be_swapped_to_refund_or_void` | `canonical.py`, `engine.py` |
| 37 | (d) | Clock skew around `exp` (+1s, wound back to `exp`), ttl 0 / negative / NaN | HELD | – | `test_clock_skew_around_expiry`, `test_non_positive_or_nan_ttl_never_makes_a_mandate` | `engine.py:execute` |
| 38 | (d) | 16 concurrent executes; executor failure then retry | HELD (1 capture; failure burns the mandate) | – | `test_concurrent_executes_of_one_mandate_capture_once`, `test_executor_failure_burns_the_mandate` | `engine.py` `_lock` |
| 39 | (d) | Ledger reorder / alter / drop middle | HELD (`altered`) | – | `test_ledger_reorder_alter_and_recomputed_chain` | `ledger.py:verify` |
| 40 | (d) | Ledger rows cut off the **end**: `/ledger` still said "intact" | FIXED (server remembers the head outside the file, in memory and in the snapshot) | medium | `test_ledger_tail_truncation_is_visible_in_the_demo_view` | `demo/app.py:_track_ledger_head`, `ledger_rows` |
| 41 | (e) store | Restart then replay; snapshot that forgot `used` | HELD (ledger is a second witness) | – | `test_security_store.py::test_restart_then_replay_is_still_a_replay`, `::test_restart_replay_survives_a_snapshot_that_forgot_…` | `demo/app.py:restore` |
| 42 | (e) | Two processes on one database both execute one approved mandate (only PayPal's idempotency key would stop the second capture) | FIXED (atomic claim in SQLite before the provider call) | medium | `test_two_processes_on_one_database_cannot_both_spend_a_mandate` | `store.py:claim_mandate`, `demo/app.py:_saved_before` |
| 43 | (e) | 8 concurrent writers; SQL injection via event ids; hostile shop ids; shops isolated | HELD | – | `test_concurrent_writers_never_corrupt_the_snapshot`, `test_sql_injection_…`, `test_hostile_shop_ids_are_refused`, `test_shops_in_one_file_…` | `store.py` |
| 44 | (e) | Write access to the database file: pair own key, forge approvals | OPEN (R2, by design) | high if the disk is lost | `test_write_access_to_the_database_is_total_trust_a_documented_residual` | `store.py`, `demo/app.py:restore` |
| 45 | (f) secrets | Credentials in `repr`, errors, pages, SQLite, ledger, banner, logs | HELD | – | `test_security_secrets.py` (9 tests) | `paypal/provider.py` |
| 46 | (f) | Secrets or key files tracked in git; databases not ignored; a stale `build/lib` copy of old code tracked | FIXED (`build/` untracked, `*.sqlite`, `build/` ignored) | low | `test_gitignore_blocks_env_and_databases`, `test_no_stale_build_tree_is_tracked`, `test_no_env_file_key_material_or_secret_literals_are_tracked` | `.gitignore` |

## Residual risks (not fixed)

| ID | Risk | Why it stays | Severity | Mitigation to do |
|---|---|---|---|---|
| R1 | Hostile **code** in the server process can reach the engine through Python introspection (`gate._execute.__self__`, closures, `gc`) | Python has no object capabilities; the guarantee is the model's tool surface (README, Limits). Sandboxing code is out of scope for a demo | High if the model could run code; none through the ten tools (tests 1–8, 10) | Run the owner side and the engine in another process; give the agent an RPC client |
| R2 | Write access to the SQLite file (or its ledger) lets someone pair their own key and forge approvals | The paired public key and signed approvals live in the same file | High if the disk is compromised | Keep the paired key in a separate, read-only config; sign the snapshot with a server key; file permissions 0600 |
| R3 | No login: anyone who can reach the demo can read mandates and press scenarios/chat | Single-shop demo; money still needs the owner's private key | Low | Put it behind auth / a private network before real use |
| R4 | A looping model can queue many identical requests or rejected executes (approval fatigue, ledger noise) | Each is its own mandate needing its own signature, capped by the held deposit | Low | Rate-limit `request_*` per booking; collapse duplicate pending asks |
| R5 | `/chat/send` reads the full body before truncating the message | Needs a size limit in a proxy | Low | Reverse-proxy body limit (or an ASGI size guard) |
| R6 | PayPal signs only the CRC32 of the body, so a colliding body verifies under the same headers; the certificate is trusted by URL host, not by a chain to a PayPal root | Inherent to the documented scheme; first-seen transmission wins, and no handler moves money. Live path against PayPal's real certificate is still unrun (README) | Low | Chain-validate the certificate; also call PayPal's `verify-webhook-signature` in the sandbox |

Also noted: a failed provider call after approval burns the mandate (by design, a second try needs a new
approval). The receipt-signing key is not persisted (README).

## How to rerun

```bash
.venv/bin/python -m pytest tests/security -q      # 192 attacker tests
.venv/bin/python -m pytest -q                     # whole suite
```

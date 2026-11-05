## N7: an attacker's pass over "the agent can never move money without the owner's mandate"

The core promise held on every attempt. The pass found 9 weaknesses around it (fixed, each with a test
that failed first) and 6 residual risks (not fixed, each pinned by a test). Full table:
`docs/SECURITY_REVIEW.md`.

### Fixed
| Weakness | Fix |
|---|---|
| Pairing code (32 bits, open endpoint) could be guessed without limit | 10 misses revoke every code (`engine.py`) |
| Cross-site form could decline mandates / press buttons | Origin / Sec-Fetch-Site check on every POST (`demo/app.py`) |
| One-tap Approve could be clickjacked | X-Frame-Options DENY, CSP, nosniff (`demo/app.py`) |
| Cert URL with a backslash parsed as paypal.com by urllib but as another host by httpx | strict URL check, same host in both parsers (`webhooks.py`) |
| `/ledger` said "intact" after rows were cut from the end | head remembered outside the file (`demo/app.py`) |
| Two processes on one SQLite file could both spend a mandate | atomic claim before the provider call (`store.py`) |
| Sub-cent cap shown as 10.00 but unrunnable | caps are whole cents (`gate.py`) |
| Non-string tool name / non-object input crashed the turn | validated (`agent/`) |
| Stale `build/lib` copy of old code tracked | untracked, ignored |

### Not fixed (see the review): R1 hostile in-process code, R2 write access to the DB, R3 no login, R4 request spam, R5 body size, R6 PayPal's CRC32-only signature.

### Evidence
- `tests/security/`: 192 tests. Whole suite: 357 passed.
- Ladders (all d = 0):
```
== N1_paypal_adapter
PASS  K10  no secrets committed  | 
d = 0/10 = 0.00
== N2_agent
PASS  K9   no secrets committed  | 
d = 0/9 = 0.00
== N3_demo
PASS  K8   no external CDN at runtime  | 
d = 0/8 = 0.00
== N4_integration
PASS  K10  no secrets committed  | 
d = 0/10 = 0.00
```
No real PayPal, no paid API, no secrets, no push to main, nothing merged.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01T6xRaQiPYC4aobnHtQGj85

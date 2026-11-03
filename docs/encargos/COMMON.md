# Rules for every work order in this repository

You are an autonomous session building one piece of Ask First Pay, an entry to the PayPal AI
Hackathon 2026 (deadline 2026-11-12). Work without asking: decide, measure, keep going. Stop only
when every criterion passes or when the only way forward is one of the forbidden acts below.

1. Read `README.md`, `docs/CONTRACT.md` and your work order. Do not read or change other pieces'
   folders (CONTRACT.md lists who owns what).
2. Setup: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"` (add your dependencies to
   `pyproject.toml`; pin a minimum version).
3. **Ladder at the start:** `python3 scripts/escalera.py docs/encargos/<your order>.md`. Keep the
   output.
4. Build. Commit small, with clear messages, on your branch. Push your branch.
5. **Ladder at the end:** same command. Every criterion should pass (`d = 0`). If one cannot pass,
   say why in one line with the command output that proves it.
6. Open a pull request against `main`. Paste both ladder outputs, what you built, what you
   measured, and anything the coordinator must decide.

Forbidden (stop and write it in the pull request instead):
- pushing to `main`, force-pushing, rewriting history;
- committing any credential, token, `.env`, or real personal data;
- calling any paid API outside the PayPal **sandbox**; spending money;
- making the repository public, publishing anything, or contacting anyone.

Before writing "blocked", "missing" or "done", run the command that proves it and paste it next
to the claim.

#!/usr/bin/env python3
"""Ladder: run every acceptance criterion of a work order and print d = failing / total.

A criterion is a markdown table row `| id | says | `command` |`: the command in backticks in the
third column passes when it exits 0. Run it at the start and at the end of a session and paste
both outputs in the pull request.

  python3 scripts/escalera.py docs/encargos/N1_paypal_adapter.md [--json]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROW = re.compile(r"^\|\s*([A-Za-z0-9_-]+)\s*\|\s*(.+?)\s*\|\s*`(.+)`\s*\|\s*$")


def criteria(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line.strip())
        if m and m.group(1).lower() not in ("id",):
            # `\|` is how a pipe is written inside a markdown table cell; the shell needs `|`.
            yield m.group(1), m.group(2), m.group(3).replace("\\|", "|")


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    root = Path(__file__).resolve().parents[1]
    rows = []
    for cid, says, cmd in criteria(Path(argv[0])):
        r = subprocess.run(["bash", "-c", cmd], cwd=root, capture_output=True, text=True, timeout=900)
        rows.append({"id": cid, "ok": r.returncode == 0, "rc": r.returncode, "says": says,
                     "tail": (r.stdout + r.stderr).strip().splitlines()[-1:] or [""]})
    total = len(rows)
    failing = sum(not r["ok"] for r in rows)
    d = failing / total if total else 1.0
    if "--json" in argv:
        print(json.dumps({"d": d, "failing": failing, "total": total, "rows": rows}, ensure_ascii=False))
    else:
        for r in rows:
            print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['id']:<4} {r['says']}  | {r['tail'][0][:100]}")
        print(f"d = {failing}/{total} = {d:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

# Adapted from src/libro_cadena.py of the public repository soyharso/agent-identity-firma.
# The mechanism is kept -- an exclusive lock (flock) taken before reading the head and released
# after writing, a single write(2) per row, and the rule that a lock not obtained diverts the
# row to a `.partial.<pid>` file instead of writing without the lock -- and so is the guarantee
# it declares: this proves CONTINUITY (nothing was deleted, reordered or altered once written),
# not authenticity; the authenticity of each mandate comes from its Ed25519 signature.
"""The hash-chained ledger of mandate uses: every row carries the hash of the previous one.

POSIX only: it relies on `fcntl.flock`.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from pathlib import Path

BUDGET_S = 10.0
WAIT_S = 0.02


def _body(row: dict) -> str:
    return json.dumps(
        {k: v for k, v in row.items() if k != "hash" and not str(k).startswith("_")},
        ensure_ascii=False, sort_keys=True,
    )


def hash_of(prev: str, row: dict) -> str:
    return hashlib.sha256((prev + _body(row)).encode("utf-8")).hexdigest()[:16]


def _write_at_once(path: Path, line: str) -> None:
    data = line.encode("utf-8")
    fd = os.open(str(path), os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        written = 0
        while written < len(data):
            written += os.write(fd, data[written:])
        os.fsync(fd)
    finally:
        os.close(fd)


class Ledger:
    """An append-only JSON-lines file whose rows are chained by hash."""

    def __init__(self, path):
        self.path = Path(path)

    def _lock(self) -> Path:
        return self.path.with_name(self.path.name + ".lock")

    def _partial(self) -> Path:
        return self.path.with_name(f"{self.path.name}.partial.{os.getpid()}.jsonl")

    def raw_rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for i, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("the row is not an object")
            except Exception as e:                               # noqa: BLE001
                row = {"_unreadable": str(e), "_raw": line[:200]}
            row["_line"] = i
            rows.append(row)
        return rows

    def _head(self) -> tuple[int, str]:
        rows = self.raw_rows()
        if not rows:
            return 0, ""
        last = rows[-1]
        return int(last.get("n") or len(rows)), str(last.get("hash") or "")

    def append(self, row: dict, budget_s: float = BUDGET_S) -> dict:
        """Appends a row (one use of a mandate). Returns the row with n/prev/hash."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        fd = os.open(str(self._lock()), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() - start >= budget_s:
                        return self._to_partial(row)
                    time.sleep(WAIT_S)
            n, prev = self._head()
            body = {k: v for k, v in row.items()
                    if not str(k).startswith("_") and k != "hash"}
            body["n"] = n + 1
            body["prev"] = prev
            body["hash"] = hash_of(prev, body)
            _write_at_once(self.path, json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n")
            return body
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def _to_partial(self, row: dict) -> dict:
        row = dict(row)
        row["out_of_chain"] = True
        row["out_of_chain_reason"] = "lock not acquired within the budget"
        _write_at_once(self._partial(),
                       json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return row

    def verify(self, expected_head: dict | None = None) -> dict:
        """Walks the chain. Says whether it holds and, if not, at which line and of what kind.

        With `expected_head` (`{"n": int, "hash": str}`, kept by the caller outside the ledger
        file) it also compares the last row with it, which is the only way to see rows removed
        from the END of the ledger (kind `truncated`). Without it, tail truncation is not
        detectable and the chain can still read as intact.
        """
        rows = self.raw_rows()
        res = {"ok": True, "broken_at": None, "message": "", "chained": 0,
               "total": len(rows), "path": str(self.path), "kind": "intact"}

        if not self.path.exists():
            res.update(ok=False, kind="missing",
                       message=f"no ledger at {self.path}: nothing to verify, "
                               f"and that is NOT an intact chain")
            return res

        prev = ""
        for row in rows:
            line = row.get("_line")
            if "_unreadable" in row:
                res.update(ok=False, kind="unreadable", broken_at=line,
                           message=f"line {line} is not readable JSON: {row['_unreadable']}")
                return res
            if str(row.get("prev", "")) != prev:
                res.update(ok=False, kind="altered", broken_at=line,
                           message=f"row n={row.get('n')} (line {line}) says it follows "
                                   f"prev={row.get('prev')!r} but the previous is {prev!r}: "
                                   f"the chain is cut, reordered or altered there")
                return res
            expected = hash_of(prev, row)
            if expected != row.get("hash"):
                res.update(ok=False, kind="altered", broken_at=line,
                           message=f"row n={row.get('n')} (line {line}) was ALTERED: its "
                                   f"content hashes to {expected} and the row says "
                                   f"{row.get('hash')}")
                return res
            prev = row["hash"]
            res["chained"] += 1

        if expected_head is not None:
            last = rows[-1] if rows else {}
            n = int(last.get("n") or len(rows)) if rows else 0
            h = str(last.get("hash") or "")
            if (n, h) != (expected_head.get("n"), expected_head.get("hash")):
                res.update(ok=False, kind="truncated",
                           message=f"the expected head is n={expected_head.get('n')} "
                                   f"hash={expected_head.get('hash')} and the ledger ends at "
                                   f"n={n} hash={h or '(empty)'}: rows were removed from the end")
                return res

        res["message"] = f"intact chain: {res['chained']} rows chained"
        return res

    def entries(self) -> list[dict]:
        """The rows, without internal annotations (`_line`, etc.)."""
        return [{k: v for k, v in row.items() if not str(k).startswith("_")}
                for row in self.raw_rows()]

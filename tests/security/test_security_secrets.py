"""(f) Secrets: nothing that could leak credentials into logs, HTML, the database, the ledger or the repo."""
import json
import re
import subprocess
from pathlib import Path

import httpx
import pytest

from ask_first_pay.demo import create_app
from ask_first_pay.paypal import PayPalProvider
from ask_first_pay.store import SqliteStore
from fastapi.testclient import TestClient

from tests.paypal.fakepaypal import MockPayPal

ROOT = Path(__file__).parents[2]
SECRET, CID, TOKEN = "S3CR3T-sandbox-value-123456", "CID-sandbox-abcdef", "A21AA-access-token-xyz"


def test_provider_repr_and_str_do_not_show_credentials():
    p = PayPalProvider(CID, SECRET, transport=httpx.MockTransport(MockPayPal()))
    for text in (repr(p), str(p), repr(p.__dict__.keys())):
        assert SECRET not in text


def test_errors_from_a_missing_or_rejected_login_do_not_echo_credentials(monkeypatch):
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    from ask_first_pay.ports import ProviderError
    with pytest.raises(ProviderError) as e:
        PayPalProvider(transport=httpx.MockTransport(MockPayPal())).create_order(10.0, "USD", "r")
    assert e.value.code == "NO_CREDENTIALS"
    bad = lambda req: httpx.Response(401, json={"error": "invalid_client", "error_description": "Client Authentication failed"})
    with pytest.raises(ProviderError) as e:
        PayPalProvider(CID, SECRET, transport=httpx.MockTransport(bad)).create_order(10.0, "USD", "r")
    assert SECRET not in f"{e.value!r} {e.value}" and CID not in f"{e.value.message}"


def test_a_full_sandbox_style_run_leaks_no_secret_into_pages_db_ledger_or_chat(tmp_path, monkeypatch):
    mock = MockPayPal()
    inner = mock.__call__
    def handler(req):
        r = inner(req)
        return r
    p = PayPalProvider(CID, SECRET, transport=httpx.MockTransport(handler))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-" + "ant-api03-FAKEFAKEFAKEFAKEFAKE")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", SECRET)
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-SECRETISH-ID-9999")
    db = str(tmp_path / "s.sqlite")
    from ask_first_pay.agent.loop import ScriptedModel
    app = create_app(p, store=SqliteStore(db, "shop"), model_factory=lambda st: ScriptedModel([]))
    c = TestClient(app)
    bodies = [c.get(path).text for path in ("/", "/chat", "/owner", "/ledger", "/owner/api/mandates", "/webhooks/paypal/events", "/healthz")]
    c.post("/chat/send", data={"message": "book Mon 16 Nov 09:00"})
    bodies.append(c.get("/chat").text)
    blob = "\n".join(bodies)
    for f in tmp_path.iterdir():
        if f.is_file():
            blob += f.read_bytes().decode("utf-8", "replace")
    for needle in (SECRET, "sk-ant-", "WH-SECRETISH-ID-9999", TOKEN):
        assert needle not in blob, needle


def test_the_demo_banner_does_not_print_credentials():
    src = (ROOT / "src/ask_first_pay/demo/__main__.py").read_text()
    prints = [l for l in src.splitlines() if "print(" in l]
    assert not [l for l in prints if re.search(r"SECRET|ANTHROPIC_API_KEY\"?\)|environ", l)]


def test_no_logging_of_requests_headers_or_bodies_in_src():
    for f in (ROOT / "src").rglob("*.py"):
        t = f.read_text()
        assert "logging" not in t and "logger" not in t, f
        for line in t.splitlines():
            if "print(" in line and f.name != "__main__.py":
                assert not re.search(r"headers|_secret|token|Authorization", line, re.I), (f, line)


def tracked():
    return subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()


def test_no_env_file_key_material_or_secret_literals_are_tracked():
    files = tracked()
    assert not [f for f in files if re.search(r"(^|/)\.env|\.pem$|\.key$|id_rsa|\.p12$|\.sqlite|\.jsonl$", f)], files
    pat = re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|(client_secret|PAYPAL_CLIENT_SECRET)\s*=\s*['\"][A-Za-z0-9_-]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|(?<![A-Za-z0-9_-])EA[A-Za-z0-9_-]{40,}")   # standalone: "REAUTHORIZATION_..." is not a token
    hits = []
    for f in files:
        p = ROOT / f
        if not p.is_file() or "vendor" in f or p.suffix in (".png", ".mp4", ".webm", ".gif", ".jpg", ".woff2", ".zip"):
            continue
        try:
            text = p.read_text("utf-8")
        except UnicodeDecodeError:
            continue
        if f != "tests/security/test_security_secrets.py" and pat.search(text):
            hits.append(f)
    assert not hits, hits


def test_gitignore_blocks_env_and_databases():
    gi = (ROOT / ".gitignore").read_text()
    assert ".env" in gi and "*.jsonl" in gi
    assert "*.sqlite" in gi, "database files hold the paired key and signed approvals"


def test_no_stale_build_tree_is_tracked():
    """FIXED: build/lib/ was a tracked copy of an OLD tree (no webhooks, no store, other app.py). A reader
    auditing the repository could read, or a tool could import, code that is not the code that runs."""
    assert not [f for f in tracked() if f.startswith("build/")]

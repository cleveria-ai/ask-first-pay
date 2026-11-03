import pytest

from ask_first import Ledger, MandateEngine, generate_pair, sign_envelope


@pytest.fixture
def person_pair():
    """TEST Ed25519 keys, generated when the test runs. Never stored."""
    return generate_pair()


@pytest.fixture
def calls():
    """Every call the injected executor received, in order."""
    return []


@pytest.fixture
def engine(tmp_path, person_pair, calls):
    def executor(mandate, requested):
        calls.append((mandate["jti"], requested))
        return {"done": True, **requested}

    return MandateEngine(
        person_pub=person_pair[1],
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        executor=executor,
    )


def approve(engine, person_pair, mandate_id, mandate=None):
    """Signs with the test private key and approves. With `mandate` None it signs what the engine
    has pending; passing a different one simulates a signature over other content.
    """
    body = mandate if mandate is not None else engine.pending[mandate_id]
    return engine.approve(mandate_id, sign_envelope(person_pair[0], body))

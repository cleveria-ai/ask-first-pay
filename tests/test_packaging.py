"""`pip install -e .` must give a judge both packages, outside pytest's pythonpath."""
import os
import subprocess
import sys


def test_packaging_installs_the_mandate_engine_and_the_demo_files(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    code = ("import ask_first, ask_first_pay.demo.app as a; "
            "assert (a.HERE / 'templates' / 'chat.html').exists(); "
            "from ask_first_pay.agent import run_turn; print('ok')")
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr

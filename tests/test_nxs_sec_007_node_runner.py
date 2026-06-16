"""NXS-SEC-007 — run the standalone Node escaping regression test as part of the
pytest suite, so the JS XSS fix is verified by the de-facto test runner (the repo
has no CI workflow). Skips cleanly if Node is not installed.
"""
import os
import shutil
import subprocess

import pytest


def test_nxs_sec_007_node_escaping_suite():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available; run `node tests/test_nxs_sec_007_xss_escaping.mjs` manually")
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(here, "test_nxs_sec_007_xss_escaping.mjs")
    r = subprocess.run([node, script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"node escaping test failed:\n{r.stdout}\n{r.stderr}"

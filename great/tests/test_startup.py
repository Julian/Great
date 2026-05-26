"""
Regression tests for CLI startup weight.

These tests don't measure wall-clock time (flaky on CI). Instead they
spawn a fresh interpreter, import a target module, and assert that
none of the known-heavy third-party packages got pulled in. A stray
``import jinja2`` at module scope is enough to fail the test, which
is exactly the kind of regression that silently re-slows
``great --version``.
"""

import json
import subprocess
import sys

import pytest

HEAVY_PACKAGES = frozenset(
    {"scipy", "numpy", "choix", "jinja2", "textual", "httpx"},
)


def _heavy_imports_after(module: str) -> frozenset[str]:
    """
    Import ``module`` in a fresh interpreter and return the heavy
    top-level packages that ended up in ``sys.modules``.
    """
    code = (
        f"import {module}, sys, json\n"
        "print(json.dumps(sorted({m.split('.', 1)[0] for m in sys.modules})))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    return HEAVY_PACKAGES & set(json.loads(proc.stdout))


@pytest.mark.parametrize(
    "module",
    [
        "great._cli",
        "great.session",
        "great.render",
        "great.albumsgenerator",
        "great.antennapod",
        "great.spotify",
    ],
)
def test_module_import_stays_lightweight(module):
    assert _heavy_imports_after(module) == frozenset(), (
        f"importing {module} pulled in a heavy package; "
        "if this is intentional, move the import inside the function "
        "that needs it (see great.session.run_rank_loop for the pattern)."
    )

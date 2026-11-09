"""The package must stay usable (CLI help, synthesis, a Pyodide app) without the heavy optional libraries.

Each check runs in a subprocess with an import hook that refuses the blocked libraries, so a top-level import
anywhere in semsynth fails the test instead of silently making the package heavier.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

_HOOK = """
import sys

class Blocker:
    def __init__(self, names):
        self.names = set(names)

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in self.names:
            raise ImportError(f"blocked in this test: {name}")

sys.meta_path.insert(0, Blocker(BLOCKED))
"""

_NOT_NEEDED_TO_IMPORT = ["statsmodels", "sklearn", "pyarrow", "jinja2", "markupsafe", "requests", "flask", "openml", "ucimlrepo"]
_NOT_NEEDED_TO_SYNTHESIZE = [name for name in _NOT_NEEDED_TO_IMPORT if name != "pyarrow"]  # polars.to_pandas needs it


def _run(blocked: list[str], code: str) -> subprocess.CompletedProcess[str]:
    script = f"BLOCKED = {blocked!r}\n" + _HOOK + textwrap.dedent(code)
    return subprocess.run([sys.executable, "-W", "ignore", "-c", script], capture_output=True, text=True, timeout=300)


def test_import_semsynth_and_the_cli_help_load_no_heavy_library() -> None:
    result = _run(
        [*_NOT_NEEDED_TO_IMPORT, "pandas", "numpy", "scipy"],
        """
        import runpy, sys
        import semsynth
        sys.argv = ["python -m semsynth", "--help"]
        try:
            runpy.run_module("semsynth", run_name="__main__")
        except SystemExit as exit_:
            assert exit_.code in (0, None), exit_.code
        """,
    )

    assert result.returncode == 0, result.stderr
    assert "build-catalog" in result.stdout


def test_library_modules_import_without_the_optional_libraries() -> None:
    modules = [
        "semsynth.synthesis", "semsynth.codebook", "semsynth.evaluate", "semsynth.preprocess", "semsynth.runner",
        "semsynth.workflow", "semsynth.datasets", "semsynth.reporting",
        "semsynth.report_tables", "semsynth.catalog", "semsynth.app", "semsynth.downstream_fidelity",
        "semsynth.missingness", "semsynth.privacy_metrics", "semsynth.umap_utils", "semsynth.mappings",
        "semsynth.dataproviders.uciml", "semsynth.dataproviders.openml", "semsynth.dataproviders.uci_archive",
        "semsynth.backends.metasyn", "semsynth.backends.privbayes", "semsynth.backends.pybnesian",
        "semsynth.backends.synthcity",
    ]
    result = _run(_NOT_NEEDED_TO_IMPORT, f"import importlib\nfor name in {modules!r}:\n    importlib.import_module(name)\n")

    assert result.returncode == 0, result.stderr


def test_missing_extras_raise_an_import_error_that_names_them() -> None:
    result = _run(
        _NOT_NEEDED_TO_IMPORT,
        """
        import pandas as pd
        from semsynth.downstream_fidelity import compute_downstream
        from semsynth.dataproviders.uci_archive import fetch_metadata
        frame = pd.DataFrame({"a": [1.0, 2.0], "b": [0.0, 1.0]})
        for call, extra in ((lambda: compute_downstream(frame, frame), "statsmodels"), (lambda: fetch_metadata(1), "providers")):
            try:
                call()
            except ImportError as exc:
                assert f"semsynth[{extra}]" in str(exc), str(exc)
            else:
                raise AssertionError(extra)
        """,
    )

    assert result.returncode == 0, result.stderr


def test_dummy_data_needs_neither_sklearn_nor_statsmodels() -> None:
    pytest.importorskip("metasyn")
    result = _run(
        _NOT_NEEDED_TO_SYNTHESIZE,
        """
        import numpy as np, pandas as pd
        from semsynth import synthesize
        rng = np.random.default_rng(0)
        frame = pd.DataFrame({"age": rng.integers(20, 80, 100).astype(float), "sex": rng.choice(["f", "m"], 100)})
        result = synthesize(frame, backend="metasyn", rows=20, seed=1)
        assert result.synthetic_data.shape == (20, 2)
        """,
    )

    assert result.returncode == 0, result.stderr

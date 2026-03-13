"""Playwright browser tests for the in-browser SPARQL endpoint on the catalog index page.

Run with:
    pytest tests/test_sparql_playwright.py --headed  # with browser visible
    pytest tests/test_sparql_playwright.py           # headless (default)

Requires a built ``output/`` directory with catalog.jsonld and sparql/*.rq files.
The tests spin up a local HTTP server so browsers can load files via http://.
"""
from __future__ import annotations

import socket
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Generator

import pytest

# ---------------------------------------------------------------------------
# Test server fixture
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
INDEX_HTML = OUTPUT_DIR / "index.html"


class _QuietHandler(SimpleHTTPRequestHandler):
    """Serve from the project root so relative paths work correctly."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def log_message(self, *args):  # silence request logs in tests
        pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def http_server() -> Generator[str, None, None]:
    """Spin up a local HTTP server serving project root and yield its base URL."""
    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _QuietHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---------------------------------------------------------------------------
# Skip guard — tests only run when output/ exists
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.skipif(
    not INDEX_HTML.exists(),
    reason="output/index.html not found; run `python -m semsynth build-catalog` first",
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
YASGUI_TIMEOUT = 20_000   # ms – time to wait for YASGUI to initialise
QUERY_TIMEOUT  = 60_000   # ms – time to wait for a Comunica query result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIndexPage:
    """Structural tests – no SPARQL execution, just DOM checks."""

    def test_no_sparql_cards_above_yasgui(self, page, http_server):
        """Query cards should NOT appear above the YASGUI editor after the fix."""
        page.goto(f"{http_server}/output/index.html")
        page.wait_for_load_state("domcontentloaded")
        assert page.locator(".sparql-card").count() == 0, (
            "sparql-card elements found above YASGUI — cards should have been removed"
        )

    def test_sparql_app_container_present(self, page, http_server):
        """The #sparql-app div must be present for YASGUI to mount into."""
        page.goto(f"{http_server}/output/index.html")
        page.wait_for_load_state("domcontentloaded")
        assert page.locator("#sparql-app").count() == 1

    def test_dataset_links_present(self, page, http_server):
        """At least 6 dataset links must appear in the index."""
        page.goto(f"{http_server}/output/index.html")
        page.wait_for_load_state("domcontentloaded")
        links = page.locator("ul li a").all()
        assert len(links) >= 6, f"Expected ≥6 dataset links, got {len(links)}"

    def test_sparql_section_heading_present(self, page, http_server):
        """The 'Static SPARQL endpoint playground' heading must be present."""
        page.goto(f"{http_server}/output/index.html")
        page.wait_for_load_state("domcontentloaded")
        heading = page.locator("h2", has_text="Static SPARQL endpoint playground")
        assert heading.count() == 1


class TestYasguiInitialisation:
    """Tests that YASGUI loads and renders query tabs from .rq files."""

    def test_yasgui_renders(self, page, http_server):
        """YASGUI should render into #sparql-app after page load."""
        page.goto(f"{http_server}/output/index.html")
        page.wait_for_selector(".yasgui", timeout=YASGUI_TIMEOUT)
        assert page.locator(".yasgui").count() >= 1

    def test_query_tabs_loaded(self, page, http_server):
        """Three query tabs (one per .rq file) should be present in YASGUI."""
        page.goto(f"{http_server}/output/index.html")
        # Wait for YASGUI and tab headers to appear
        page.wait_for_selector(".yasgui .tabsList .tab", timeout=YASGUI_TIMEOUT)
        tabs = page.locator(".yasgui .tabsList .tab").all()
        assert len(tabs) >= 3, (
            f"Expected ≥3 YASGUI tabs (one per .rq file), found {len(tabs)}"
        )

    def test_first_tab_has_query_content(self, page, http_server):
        """The first tab's editor must contain a non-empty SPARQL query."""
        page.goto(f"{http_server}/output/index.html")
        page.wait_for_selector(".CodeMirror-lines", timeout=YASGUI_TIMEOUT)
        editor_text = page.locator(".CodeMirror-lines").first.inner_text()
        assert "SELECT" in editor_text.upper() or "PREFIX" in editor_text.upper(), (
            "First YASGUI tab does not appear to contain a SPARQL query"
        )

    def test_tab_names_match_rq_files(self, page, http_server):
        """Tab names should correspond to the named queries in exampleQueries."""
        page.goto(f"{http_server}/output/index.html")
        page.wait_for_selector(".yasgui .tabsList .tab", timeout=YASGUI_TIMEOUT)
        # Collect tab label text
        tab_names = [
            t.inner_text().strip()
            for t in page.locator(".yasgui .tabsList .tab").all()
            if t.inner_text().strip()
        ]
        expected_substrings = ["SemMap coverage", "Provenance", "SemMap + provenance"]
        for sub in expected_substrings:
            assert any(sub.lower() in name.lower() for name in tab_names), (
                f"No tab with name containing '{sub}'. Found tabs: {tab_names}"
            )


class TestSparqlExecution:
    """Execute SPARQL queries via the Comunica engine and verify results."""

    def _run_query_on_first_tab(self, page, http_server):
        """Load index, wait for YASGUI, run query on first tab, return result element."""
        page.goto(f"{http_server}/output/index.html")
        page.wait_for_selector(".CodeMirror-lines", timeout=YASGUI_TIMEOUT)
        # Trigger execution via keyboard shortcut (Ctrl+Enter)
        page.locator(".CodeMirror").first.click()
        page.keyboard.press("Control+Enter")
        # Wait for the result element injected by runWithComunica
        page.wait_for_selector(".semsynth-query-result", timeout=QUERY_TIMEOUT)
        return page.locator(".semsynth-query-result").first

    def test_semmap_coverage_query_returns_results(self, page, http_server):
        """The SemMap coverage query must return SPARQL results (not an error)."""
        result_el = self._run_query_on_first_tab(page, http_server)
        result_text = result_el.inner_text()
        assert '"error"' not in result_text.lower() or "results" in result_text.lower(), (
            f"Query returned error: {result_text[:300]}"
        )
        # Result should be JSON-like (SPARQL results JSON format)
        assert result_text.strip().startswith("{") or "bindings" in result_text, (
            f"Unexpected result format: {result_text[:300]}"
        )

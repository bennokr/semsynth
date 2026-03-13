"""Playwright tests for the in-browser SPARQL interface.

Starts a local HTTP server with correct MIME types (including application/ld+json
for .jsonld files) and verifies that YASGUI loads, query tabs are populated from
.rq assets, and Comunica can execute a SPARQL query against catalog.jsonld.
"""

from __future__ import annotations

import mimetypes
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"

# Ensure .jsonld is served with the correct media type so Comunica can parse it.
mimetypes.add_type("application/ld+json", ".jsonld")
mimetypes.add_type("application/sparql-query", ".rq")

YASGUI_TIMEOUT = 25_000  # ms to wait for YASGUI to initialise
QUERY_TIMEOUT = 90_000   # ms to wait for query results


class _MimeAwareHandler(BaseHTTPRequestHandler):
    """Minimal static file server that respects known MIME overrides."""

    def log_message(self, *_args) -> None:  # silence access logs in tests
        pass

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].lstrip("/")
        target = (PROJECT_ROOT / path).resolve()
        # Prevent path traversal.
        if not str(target).startswith(str(PROJECT_ROOT)):
            self.send_error(403)
            return
        if not target.is_file():
            self.send_error(404)
            return
        mime, _ = mimetypes.guess_type(str(target))
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server_url():
    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _MimeAwareHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(scope="module")
def index_page(browser, server_url):
    context = browser.new_context()
    page = context.new_page()
    page.goto(f"{server_url}/output/index.html", wait_until="networkidle")
    yield page
    context.close()


# ---------------------------------------------------------------------------
# Index page structure
# ---------------------------------------------------------------------------

class TestIndexPage:
    def test_no_sparql_cards_above_yasgui(self, index_page):
        """Query cards must NOT appear as .sparql-card elements above YASGUI."""
        cards = index_page.query_selector_all(".sparql-card")
        assert len(cards) == 0, f"Expected 0 .sparql-card elements, found {len(cards)}"

    def test_sparql_app_container_present(self, index_page):
        assert index_page.query_selector("#sparql-app") is not None

    def test_dataset_links_present(self, index_page):
        links = index_page.query_selector_all("ul li a")
        assert len(links) >= 5, f"Expected ≥5 dataset links, got {len(links)}"

    def test_sparql_section_heading_present(self, index_page):
        headings = [
            h.inner_text()
            for h in index_page.query_selector_all("h2")
        ]
        assert any("SPARQL" in h for h in headings), f"No SPARQL heading found; headings: {headings}"


# ---------------------------------------------------------------------------
# YASGUI initialisation
# ---------------------------------------------------------------------------

class TestYasguiInitialisation:
    def test_yasgui_renders(self, index_page):
        index_page.wait_for_selector(".yasgui", timeout=YASGUI_TIMEOUT)

    def test_query_tabs_loaded(self, index_page):
        index_page.wait_for_selector(".yasgui .tabsList .tab", timeout=YASGUI_TIMEOUT)
        tabs = index_page.query_selector_all(".yasgui .tabsList .tab")
        assert len(tabs) >= 3, f"Expected ≥3 query tabs, found {len(tabs)}"

    def test_first_tab_has_query_content(self, index_page):
        editor = index_page.query_selector(".yasgui .CodeMirror")
        assert editor is not None
        text = editor.inner_text()
        assert any(kw in text.upper() for kw in ("SELECT", "PREFIX")), \
            f"Expected SPARQL keywords in editor, got: {text[:200]}"

    def test_tab_names_match_rq_files(self, index_page):
        # YASGUI renders tab names as <span> children of each .tab anchor.
        tabs = index_page.query_selector_all(".yasgui .tabsList .tab a span")
        tab_names = [t.inner_text().strip() for t in tabs if t.inner_text().strip()]
        rq_files = sorted(p.stem for p in (OUTPUT_DIR / "sparql").glob("*.rq"))
        assert len(tab_names) >= len(rq_files), \
            f"Expected ≥{len(rq_files)} named tabs, got {len(tab_names)}: {tab_names}"


# ---------------------------------------------------------------------------
# SPARQL execution
# ---------------------------------------------------------------------------

class TestSparqlExecution:
    def test_semmap_coverage_query_returns_results(self, browser, server_url):
        """Run the first query tab via Ctrl+Enter and verify output appears."""
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(f"{server_url}/output/index.html", wait_until="networkidle")
            page.wait_for_selector(".yasgui .CodeMirror", timeout=YASGUI_TIMEOUT)
            page.keyboard.press("Control+Enter")
            page.wait_for_selector(".semsynth-query-result", timeout=QUERY_TIMEOUT)
            result_text = page.query_selector(".semsynth-query-result").inner_text()
            assert result_text.strip(), "Expected non-empty query results"
        finally:
            context.close()

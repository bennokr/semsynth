import os
import sys

# --- make your package importable ---
sys.path.insert(0, os.path.abspath(".."))

# --- basic project info ---
project = "semsynth"
author = "SemSynth Authors"

# --- extensions ---
extensions = [
    "myst_nb",              # MyST notebooks (includes Markdown parser)
    "sphinx.ext.autodoc",   # pull in docstrings
    "sphinx.ext.autosummary",  # generate API pages
    "sphinx.ext.napoleon", # docstrings
]

# Parse both .rst and .md (MyST-NB handles Markdown/nbformat)
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "myst-nb",
    ".ipynb": "myst-nb",
}

# Root document
root_doc = "index"          # Sphinx ≥4
master_doc = "index"        # backward compatibility

# MyST options (optional but common)
myst_enable_extensions = [
    "linkify",
]

# Auto-anchor headings for internal cross-references in included docs
myst_heading_anchors = 3

# Execute notebooks automatically and fail on cell errors
nb_execution_mode = "auto"
nb_execution_allow_errors = False

# Automatically generate autosummary stub files
autosummary_generate = True
autosummary_imported_members = True

# (Optional) slightly nicer autodoc defaults
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}

html_theme = "sphinx_rtd_theme"

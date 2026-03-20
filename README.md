# SemSynth 🚀

SemSynth is a compact toolkit to profile tabular datasets, synthesize data with multiple backends, and generate a clean HTML report. It supports datasets from OpenML and the UCI Machine Learning Repository.

## ✨ Features
- Unified model interface: run PyBNesian, SynthCity, and MetaSyn models from a single TOML bundle.
- Uniform outputs: each model writes artifacts under `dataset/models/<model-name>/`.
- Optional MetaSyn baseline: enable or disable per report via the config bundle.
- Provider-aware metadata and UMAP visuals.

## ⚙️ Install
Clone and run `python -m pip install -e .`

For extra features, run `python -m pip install -e .[EXTRA]` with `EXTRA` in (
`app`
`metasyn`
`pybnesian`
`synthcity`
`umap`
`statsmodels`
`mapping`).

## 🔎 Quick start

1. Search datasets
   - OpenML: `python -m semsynth search openml --name-substr adult`
   - UCI ML: `python -m semsynth search uciml --area "Health and Medicine" --name-substr heart`

   The `search` command accepts:
   - `--name-substr` (substring filter applied case-insensitively)
   - `--area` (UCI ML topic area, ignored for OpenML)
   - `--cat-min` / `--num-min` (minimum categorical/numeric columns)
   - `--verbose` (emits info logs while querying providers)

2. Minimal report (metadata only) 🧪
   - Leave `--configs-toml` empty to skip model execution.
   - Example: `python -m semsynth report uciml --datasets 45 -v`
   - Optional flags for reports:
     - `--datasets` (one or more dataset identifiers)
     - `--outdir` (defaults to `output/`)
     - `--configs-toml` (path to a TOML bundle; omit for metadata-only runs)
     - `--verbose` (turn on info logging)

   With the command above you receive dataset metadata, a real-data UMAP projection, and HTML/Markdown reports under `output/<Dataset Name>/`.

3. Full report with synthetic models 🤖
    - Pick a configuration bundle from `configs/`:
      - `configs/simple_config.toml` (MetaSyn + two PyBNesian models)
      - `configs/advanced_config.toml` (MetaSyn, PyBNesian, and SynthCity models)
      - `configs/maximal_config.toml` (keeps MetaSyn with aggressive options enabled while remaining runnable without GPU or shared-memory support)
      - `configs/only_metasyn_config.toml` (MetaSyn baseline only)
   - Example: `python -m semsynth report openml --datasets adult --configs-toml @configs/advanced_config.toml`

   Pipeline toggles (UMAP, privacy, downstream, missingness, SemMap context URL, etc.) now live in the TOML bundle under `[pipeline]` rather than separate CLI flags.

4. Catalog + app helpers
   - Build a DCAT catalog and HTML index from existing outputs: `python -m semsynth build-catalog`
   - Regenerate metadata-only reports for all curated SemMap mappings and refresh the catalog/index: `python -m semsynth mappings --pipeline-configs ""`
   - Re-render reports for all curated mappings using existing outputs (skip mappings and metrics): `python -m semsynth refresh-mapping-reports --pipeline-configs '{pipeline={generate_umap=false,compute_privacy=false,compute_downstream=false,overwrite_umap=false}}'`
   - The generated `output/index.html` now embeds **YASGUI + Comunica (browser)** with a static endpoint identifier (`browser://semsynth-static-catalog`) and loads runnable query tabs from `output/sparql/*.rq` files for SemMap and provenance-linked synthetic artifacts.
   - Launch a minimal Flask UI for search and report actions: `python -m semsynth app --host 0.0.0.0 --port 5000`

## 📄 TOML bundles
- `configs/simple_config.toml` mixes MetaSyn with two PyBNesian baselines.
- `configs/advanced_config.toml` extends the simple bundle with SynthCity generators.
- `configs/maximal_config.toml` toggles every optional report hook (UMAP, privacy, downstream) but ships with a MetaSyn-only bundle so it continues to execute inside restricted environments.
- `configs/only_metasyn_config.toml` keeps MetaSyn as the single synthetic data baseline.

Example:

```toml
[[models]]
name = "metasyn"
backend = "metasyn"

[[models]]
name = "clg_mi2"
backend = "pybnesian"
rows = 1000
seed = 42

[models.model]
type = "clg"
score = "bic"
operators = ["arcs"]
max_indegree = 2

[[models]]
name = "ctgan_fast"
backend = "synthcity"
rows = 1000
seed = 42

[models.model]
type = "ctgan"
epochs = 5
batch_size = 256

[pipeline]
generate_umap = true
compute_privacy = true
compute_downstream = true
semmap_context_url = "https://w3id.org/semmap/context"
```

## 📦 Outputs
- Per dataset (e.g., `output/Heart Disease/`):
  - `index.html` and `report.md`
  - `dataset.semmap.json` and `dataset.semmap.html` (when SemMap metadata is available)
  - `umap_real.png` (when `--generate-umap` is enabled and UMAP dependencies are installed)
- Per model (e.g., `output/Heart Disease/models/<name>/`):
  - `synthetic.csv`, `metrics.json`, and `umap.png`
  - Optional metrics sidecars: `metrics.privacy.json`, `metrics.downstream.json`
  - PyBNesian extras: `structure.png`, `structure.graphml`, `model.pickle`
  - `synthetic.semmap.parquet` (when SemMap metadata is available)

## 🧰 Metadata templates & column mappings
- `semsynth/dataproviders/uciml.py` exposes a CLI that turns the JSON payloads cached under `uciml-cache/` (sometimes referenced as `uci-cache/` in earlier docs) into DCAT + DSV JSON-LD that downstream tools can ingest.
- Scripts under `map_columns/` take that JSON-LD and suggest or write terminology mappings (see `map_columns/README.md` for the full strategy catalog covering lexical, Datasette keyword, embedding, and LLM workflows).
- `python -m semsynth create-mapping uciml --datasets 145 --method lexical` automates the end-to-end workflow (JSON-LD export → terminology scoring → SSSOM merge) and stores the results under `mappings/`.
- Curated SemMap JSON files are repo-only under `mappings/` and are not bundled into wheels; when installing from PyPI, provide your own `mappings/` directory if you want curated mappings.

### Example: UCI dataset 45 (Heart Disease)
1. Fetch the dataset metadata. Any command that touches the UCI provider will populate `uciml-cache/<id>.json`. For example:

   ```bash
   python -m semsynth report uciml --datasets 45 --configs-toml @configs/only_metasyn_config.toml
   ```

   This creates `uciml-cache/45.json` alongside the cached CSV/metadata used by the reporting pipeline.
2. Convert the cached metadata into DCAT + DSV JSON-LD:

   ```bash
   python semsynth/dataproviders/uciml.py uciml-cache/45.json heart-dataset.jsonld
   ```
   The resulting `heart-dataset.jsonld` contains dataset-level `dcat:Dataset` fields plus a `dsv:datasetSchema` block with each variable from the Heart Disease dataset.
3. Suggest terminology mappings for every variable description using the keyword search helper (writes SSSOM when `--output` is provided):
   
   ```bash
   python map_columns/kwd_map_columns.py heart-dataset.jsonld \
       --datasette-db-url http://127.0.0.1:8001/terminology \
       --table codes \
       --limit 10 \
       --top-k 3 \
       --output mappings/uciml-45.keyword.sssom.tsv \
       --verbose
   ```
   Swap in `map_columns/embed_map_columns.py` or `map_columns/llm_map_columns.py` to use embedding or LLM variants (see `map_columns/README.md` for full parameter lists).
4. Run the integrated helper to write mappings and SemMap metadata in one go:

   ```bash
   python -m semsynth create-mapping uciml \
       --datasets 45 \
       --method embed \
       --codes-tsv map_columns/codes.tsv \
       --datasette-url http://127.0.0.1:8001/terminology \
       --lexical-threshold 0.25 \
       --top-k 3 \
       --verbose
   ```
   The resulting files (e.g., `mappings/uciml-45.sssom.tsv`) can be fed back into the reporting pipeline without extra steps.

## 📝 Notes
- Metadata-only reports require no TOML file; pass `--configs-toml` to opt into synthetic runs.
- All models are treated uniformly in the report; UMAPs share the same projection trained on real data.
- When optional dependencies (e.g., `umap-learn`, PyBNesian, SynthCity) are missing or blocked by runtime sandboxing, SemSynth logs a warning and continues with the available components. The shipped `maximal_config` keeps MetaSyn as the default to guarantee completion under those constraints.
- UCI dataset 1150 (Gallstone) is currently unavailable via `ucimlrepo`; the `mappings` target skips it with a warning until a cached stand-in or upstream access is restored.
- If external dataset hosts are unreachable, cached payloads under `downloads-cache/` may contain synthetic stand-ins that mimic the documented schema so pipeline checks can proceed. Keep README notes in sync when such fallbacks are introduced.

## 📚 Testing, Contributing, Documentation
- Install dev and documentation deps with `python -m pip install -e .[dev,docs]` (use `.[dev]` if you do not need to build docs).
- Run tests with `python -m pytest`
- Build the Sphinx site with `sphinx-build -b html sphinx docs`.

## 🔎 Static SPARQL endpoint (demo index)
- `python -m semsynth build-catalog` writes `output/index.html`, `output/catalog.json`, `output/catalog.jsonld`, and `output/sparql/*.rq` with an embedded YASGUI editor and browser Comunica query engine targeting static files only.
- The page advertises endpoint id `browser://semsynth-static-catalog` and includes ready-to-run query tabs covering:
  - datasets that publish `dataset.semmap.json`,
  - provenance-linked synthetic artifacts,
  - distribution counts per dataset.
- This mirrors the static-browser pattern from `data-catalog-sparql-playground` (catalog + local query UI, no server-side SPARQL service required).
- SPARQL query templates are also described as catalog distributions so tooling can discover and preload them as tabs.

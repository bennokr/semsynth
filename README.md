# SemSynth 🚀

SemSynth is a compact toolkit to profile tabular datasets, synthesize data with multiple backends, and generate a clean HTML report. It supports datasets from OpenML and the UCI Machine Learning Repository.

## ✨ Features
- Unified model interface: run PyBNesian, SynthCity, and MetaSyn models from a single TOML bundle.
- Uniform outputs: each model writes artifacts under `dataset/models/<model-name>/`.
- Optional MetaSyn baseline: enable or disable per report via the config bundle.
- Provider-aware metadata and UMAP visuals.

## ⚙️ Install
Clone and run `python -m pip install -e .`

The core (`import semsynth`, `python -m semsynth --help`, synthesizing from a DataFrame) needs only numpy, pandas,
scipy, scikit-learn, pyarrow, jinja2, markdown, makeprov and linked-codebook, and imports them when a feature needs
them. Everything else is an extra: `python -m pip install -e .[EXTRA]` with `EXTRA` in

| extra | adds |
| --- | --- |
| `providers` | `openml`, `ucimlrepo`, `requests`: load and search OpenML and UCI ML datasets (all of `search`, `report`) |
| `app` | `flask`: `python -m semsynth run-app` |
| `metasyn`, `privbayes` | the MetaSyn and DataSynthesizer (PrivBayes) backends |
| (none) | the `chain` backend (a tree per column given the columns before it, as in synthpop) needs only scikit-learn, which is a core dependency, and runs in Pyodide |
| `pybnesian` | the PyBNesian backend (NumPy 2) |
| `dp_cgans` | the DP-CGANS backend (a conditional GAN with optional DP-SGD, with its privacy budget in `privacy_report`): needs PyTorch (a CPU build is enough), NumPy 2, and does not run in Pyodide; its dependency `copulas` is BUSL-1.1 |
| `mostlyai` | the MOSTLY AI TabularARGN backend (experimental): a neural model; needs PyTorch (a CPU build is enough), NumPy 2, and does not run in Pyodide |
| `synthcity` | the SynthCity backend; heavy (PyTorch) and the one extra that needs NumPy below 2, so it cannot share an environment with `pybnesian`, `umap`, `language`, `privacy` or `all` (uv enforces this in `[tool.uv] conflicts`) |
| `statsmodels` | the downstream coefficient comparison |
| `privacy` | `sdmetrics`: attribute-inference and distance-to-closest-record scores (NumPy 2; runs in Pyodide). Without it the exact-match and distance statistics are still computed, and the sdmetrics block of `metrics.privacy.json` says `skipped` |
| `umap` | UMAP plots |
| `language` | `py3langid`: records the language of text columns in the profile (`dct:language`, linked-codebook 0.10), and MetaSyn then draws free text in that language instead of English |
| `mapping` | `entailmap.match`, for `create-mapping` |

A missing extra raises an `ImportError` that names it. `python -m semsynth report ...` therefore needs
`.[providers]` plus the extras of the models and metrics it runs.

Dataset metadata is a [linked-codebook](https://bennokr.github.io/linked-codebook/) profile (see `sphinx/schema.md`). linked-codebook needs Python 3.11 or newer and is not on PyPI yet, so the dependency points to its published wheel. That also means SemSynth itself cannot be published to PyPI until linked-codebook is.

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
   - Leave `--pipeline-configs` empty to skip model execution.
   - Example: `python -m semsynth report uciml --datasets 45 -v`
   - Optional flags for reports:
     - `--datasets` (one or more dataset identifiers)
     - `--outdir` (defaults to `output/`)
     - `--pipeline-configs` (path to a TOML bundle; omit for metadata-only runs)
     - `--verbose` (turn on info logging)

   With the command above you receive dataset metadata, a real-data UMAP projection, and HTML/Markdown reports under `output/<dataset-slug>/` (the slug of the dataset name, such as `heart-disease`).

3. Full report with synthetic models 🤖
    - Pick a configuration bundle from `configs/`:
      - `configs/minimal_config.toml` (a report of the data only, no model)
      - `configs/simple_config.toml` (MetaSyn and the chain generator; the quick start)
      - `configs/demo_config.toml` (MetaSyn, the chain and one PyBNesian model, cross-validated; the demo site is built with it)
      - `configs/full_config.toml` (every generator that shares one NumPy 2 environment, including MOSTLY AI)
      - `configs/synthcity_config.toml` (SynthCity generators; needs NumPy 1, so its own environment)
   - Example: `python -m semsynth report openml --datasets adult --pipeline-configs configs/simple_config.toml`

   Pipeline toggles (UMAP, privacy, downstream, missingness, etc.) now live in the TOML bundle under `[pipeline]` rather than separate CLI flags.

4. Catalog + app helpers
   - Break a complete table in known ways and check what the pipeline recovers (injected-truth benchmark, see the documentation): `python -m semsynth benchmark` (a demo table, about 4 seconds) or `python -m semsynth benchmark table.csv --mechanisms mechanisms.toml --backend chain`
   - Build a DCAT catalog (`output/catalog.json`) and an index page from existing outputs: `python -m semsynth build-catalog`
   - Regenerate metadata-only reports for all curated codebooks and refresh the catalog/index: `python -m semsynth mappings --pipeline-configs ""`
   - Re-render reports for all curated mappings using existing outputs (skip mappings and metrics): `python -m semsynth refresh-mapping-reports --pipeline-configs '{pipeline={generate_umap=false,compute_privacy=false,compute_downstream=false,overwrite_umap=false}}'`
   - Launch a minimal Flask UI for search and report actions (needs `.[app,providers]`): `python -m semsynth run-app --port 5000`. It calls the same functions as `search` and `report`, accepts inline TOML only, and binds to 127.0.0.1 unless you pass `--host`

## 📄 TOML bundles
- `configs/minimal_config.toml` reports on the data only: no model is fitted.
- `configs/simple_config.toml` is the quick start: MetaSyn and the chain generator (which needs no extra), one split of the data.
- `configs/demo_config.toml` adds one PyBNesian model and the cross-validated evaluation (5 folds, intervals, references); the demo site is built with it.
- `configs/full_config.toml` has every generator that shares one NumPy 2 environment: MetaSyn, the chain, two PyBNesian networks and MOSTLY AI.
- `configs/synthcity_config.toml` has the SynthCity generators; install `.[synthcity]` in its own environment (it needs NumPy 1).

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
compute_joint = true        # pairwise dependence, missingness structure, classifier two-sample test
compute_baselines = true    # score the synthetic table next to a real sample and independent marginals
bootstrap_reps = 200        # resamples and random splits behind the intervals and noise floors
compute_utility = true      # train on the synthetic rows, predict the target of real rows; with ceiling, floor and interval
cv_folds = 5                # k-fold cross-validation of every model: scores are the mean over the folds with an interval
privacy_missing = "category"  # missing values in distances: category, observed or asymmetric (or a table by column)
sensitive_columns = []          # columns that the attribute-inference privacy check tries to infer (needs the privacy extra)
structure_aware = false     # learn across the codebook's skip rules (applies_when) and enforce them on the output
compute_subgroups = false   # per-subgroup fidelity and privacy; subgroups come from the codebook and `subgroups`
subgroups = [{ name = "older", condition = "[age] >= 65" }]
subgroup_min_size = 30
```

## 📦 Outputs
- Per dataset (e.g., `output/heart-disease/`):
  - `index.html` and `report.md`
  - `dataset.codebook.jsonld` (DSV JSON-LD written by linked-codebook) and its RDFa rendering `dataset.codebook.html`
  - `umap_real.png` (when `--generate-umap` is enabled and UMAP dependencies are installed)
- Per model (e.g., `output/heart-disease/models/<name>/`):
  - `synthetic.csv`, `metrics.json`, and `umap.png`
  - Optional metrics sidecars: `metrics.privacy.json`, `metrics.downstream.json`, `metrics.joint.json`, `metrics.baselines.json`, `metrics.subgroups.json`; `metrics.json` holds `utility` and `cv` (see the evaluation page of the documentation for what each score means and how to read it)
  - PyBNesian extras: `structure.png`, `structure.graphml` (and `model.pickle` with the model setting `save_model = true`; it is not written by default, because a pickle can run code when loaded)
  - `synthetic.parquet`, with the codebook JSON-LD in the Parquet schema metadata

## 🧰 Metadata templates & column mappings
- `semsynth/dataproviders/uciml.py` exposes a CLI that turns the JSON payloads cached under `uciml-cache/` (sometimes referenced as `uci-cache/` in earlier docs) into DCAT + DSV JSON-LD that downstream tools can ingest.
- Terminology matching (lexical, Datasette keyword, embedding and LLM strategies) lives in [entailmap](https://github.com/bennokr/entailmap) as `entailmap.match`. Install it with `pip install "semsynth[mapping]"`. This repository keeps only the terminology data in `map_columns/` (`codes.tsv`, `terminology.db`) until it becomes a release asset of entailmap; `ENTAILMAP_MATCH_DATA` can point elsewhere.
- `python -m semsynth create-mapping uciml --datasets 145 --method lexical` automates the end-to-end workflow (JSON-LD export → terminology scoring → SSSOM merge) and stores the results under `mappings/`.
- Curated codebooks (`mappings/*.metadata.json`, DSV JSON-LD) are repo-only under `mappings/` and are not bundled into wheels; when installing from PyPI, provide your own `mappings/` directory if you want curated mappings.

### Example: UCI dataset 45 (Heart Disease)
1. Fetch the dataset metadata. Any command that touches the UCI provider will populate `uciml-cache/<id>.json`. For example:

   ```bash
   python -m semsynth report uciml --datasets 45 --pipeline-configs configs/simple_config.toml
   ```

   This creates `uciml-cache/45.json` alongside the cached CSV/metadata used by the reporting pipeline.
2. Convert the cached metadata into DCAT + DSV JSON-LD:

   ```bash
   python semsynth/dataproviders/uciml.py uciml-cache/45.json heart-dataset.jsonld
   ```
   The resulting `heart-dataset.jsonld` contains dataset-level `dcat:Dataset` fields plus a `dsv:datasetSchema` block with each variable from the Heart Disease dataset.
3. Suggest terminology mappings for every variable description with entailmap (writes SSSOM):

   ```bash
   entailmap match keyword heart-dataset.jsonld \
       --datasette-url http://127.0.0.1:8001/terminology \
       --top-k 3 -o mappings/uciml-45.keyword.sssom.tsv
   ```
   Use `lexical`, `embed` or `llm` instead of `keyword` for the other strategies; see `entailmap match --help`.
4. Run the integrated helper to write mappings and the codebook in one go:

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
- Metadata-only reports require no TOML file; pass `--pipeline-configs` to opt into synthetic runs.
- All models are treated uniformly in the report; UMAPs share the same projection trained on real data.
- When optional dependencies (e.g., `umap-learn`, PyBNesian, SynthCity) are missing or blocked by runtime sandboxing, SemSynth logs a warning and continues with the available components. The shipped `maximal_config` keeps MetaSyn as the default to guarantee completion under those constraints.
- Downloads verify TLS certificates. On a network with an intercepting proxy, set `SEMSYNTH_INSECURE_UCI=1` to make `ucimlrepo` skip verification (it logs a warning).
- Some UCI datasets, such as 1150 (Gallstone), have no `data_url`, so `ucimlrepo` cannot import them. SemSynth then downloads the published archive and reads the table from it (`semsynth/dataproviders/uci_archive.py`; run `python -m semsynth.dataproviders.uci_archive 1150` to fill the cache).
- If external dataset hosts are unreachable, cached payloads under `downloads-cache/` may contain synthetic stand-ins that mimic the documented schema so pipeline checks can proceed. Keep README notes in sync when such fallbacks are introduced.

## 📚 Testing, Contributing, Documentation
- Install dev and documentation deps with `python -m pip install -e .[dev,docs]` (use `.[dev]` if you do not need to build docs).
- Run tests with `python -m pytest`
- Build the Sphinx site with `sphinx-build -b html sphinx docs`.
- The published site (demo reports for the curated datasets, the catalog, the explorer and the documentation) is built by `.github/workflows/pages.yml` on every push to `main`. The reports take hours, so they are not built there: see "Publishing the site" below. `output/`, `dist-site/` and `docs/` are not committed.

### Publishing the site
The workflow pulls the reports from the latest release, so publishing is a build on your machine and an upload:

```bash
make site                      # builds output/ with configs/demo_config.toml, checks it and writes dist-site/ (needs a clean commit)
gh release create site-2026-11-20 dist-site/semsynth-site.tar.gz dist-site/semsynth-site.tar.gz.sha256 \
  --title "Demo reports 2026-11-20" --notes "Built from $(git rev-parse --short HEAD) with configs/demo_config.toml"
```

Then push to `main`, or run the `pages` workflow by hand (`gh workflow run pages.yml`; give `-f tag=<release>` for a release that is not the latest). The workflow downloads `semsynth-site.tar.gz`, unpacks it only if it matches its checksum and holds nothing but `output/`, `downloads-cache/` and `site-manifest.json` (`scripts/site_bundle.py`), checks that every model has its privacy, baseline and provenance files (`scripts/check_output.py`), builds the documentation and the explorer around it, and publishes the manifest (commit, date, configuration) at `site-manifest.json`. A notebook of the documentation that fails to run fails the build. `make site-bundle` packs an existing `output/` without building it again; the documentation notebooks read `downloads-cache/uciml/45.csv.gz`, which the bundle carries.

## 🔎 SPARQL over the output
- Everything that is published has an IRI under one base (`iri_base`, default `https://bennokr.github.io/semsynth/output/`, see `semsynth/iris.py`): `<base><dataset>/` is the dataset (its codebook describes it), `<base><dataset>/models/<model>/` the synthetic dataset, `…/#run` the run that made it. Folder names are slugs, so no IRI has a space; titles are in `dct:title`.
- The catalog (DCAT), the codebooks (DSV, written by linked-codebook) and the provenance of each run (PROV-O, with the scores as W3C DQV measurements) use those same IRIs, so SPARQL joins them directly. `queries/*.rq` holds the example queries; none of them takes a string apart.
- The explorer at `explore/` is the [data-catalog-sparql-playground](https://github.com/bennokr/data-catalog-sparql-playground) (Comunica and YASGUI in the browser, no server), built in the Pages workflow from the JSON-LD files of `output/` (the catalog, the codebooks, the provenance of each run and the makeprov record) and `queries/`. The playground merges its sources into one graph in the browser, so a triple that two files state is returned once.
- To try it locally: `python -m semsynth build-catalog`, then build the playground with its `make_catalog.py build --data 'output/catalog.json' --data 'output/*/dataset.codebook.jsonld' --data 'output/*/models/*/provenance.json' --queries 'queries/*.rq'` and serve the result.



## Synthesizing from Python

```python
from semsynth import synthesize
from semsynth.synthesis import write_run

result = synthesize(df, codebook, backend="metasyn", rows=500, seed=1)   # or "privbayes", "pybnesian", "mostlyai", "chain", "synthcity", "dp_cgans"
result.synthetic_data      # a pandas DataFrame
result.learned_model       # backend-specific object
write_run(result, "output/run-1")   # only if you want the files
```

What a backend can do is listed in `semsynth.synthesis.CAPABILITIES` (`capabilities("chain")`): whether it accepts blanks, whether
it learns categories, whether it runs in Pyodide, and whether it has a differential-privacy option. A package can add a backend
without a change here: it provides a module (or `module:object`) with `synthesize(df, codebook, *, rows, seed, **options)`, which
returns a `SynthesisResult` and may declare `CAPABILITIES`, and registers it as an entry point:

```toml
[project.entry-points."semsynth.backends"]
mygan = "mypackage.semsynth_backend"
```

`backend="mygan"` then works in `synthesize` and in a TOML config. `tests/test_backend_contract.py` shows what every backend has to do
(the columns, the rows, the kinds of values); copy its check into the tests of the plugin.

`synthesize` never touches the disk, so it also runs in a browser (Pyodide). Every backend module defines
`synthesize(df, codebook, *, rows, seed, **options)` and returns a `semsynth.SynthesisResult`: the generated data
and the learned model as Python objects, alongside parameters, utility metrics, privacy facts, provenance, semantic
actions, and warnings. `write_run` is the one function that serializes a result (`synthetic.csv`, metrics,
`manifest.json`, a PROV-O `provenance.json`, ...); the report pipeline uses it.

MetaSyn learns one distribution per column and is the choice for dummy data with realistic types, ranges and
missingness. It carries no privacy claim. PrivBayes (`pip install -e ".[privbayes]"`) is differentially private
for the budget `epsilon` you give it. PyBNesian (`.[pybnesian]`) learns a Bayesian network (`type="clg"` or
`"semiparametric"`) and keeps its GraphML, picture and pickle as artifacts; SynthCity (`.[synthcity]`, heavy: PyTorch)
runs one of its generators (`type="ctgan"`, `"tvae"`, `"adsgan"`, `"bn"`, ...). PyBNesian is tested in CI; SynthCity is
tested by the weekly canary, because its install is several gigabytes.

Declared semantic bins, datatypes, and categorical flags are applied before
PrivBayes learns its network. The result records those computational actions so
downstream tools can distinguish semantics that affected computation from
metadata used only for display.

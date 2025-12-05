# Column Terminology Mapping

The `map_columns/` directory contains utilities for building terminology
resources, mapping dataset columns to codes, and evaluating the resulting SSSOM
artifacts. The tooling supports offline TSV lookups, Datasette-backed keyword
search, embedding re-ranking, and LLM-assisted coding.

## Table of Contents

- [Scripts Overview](#scripts-overview)
- [Prerequisites](#prerequisites)
- [Usage](#usage)
  - [1. Build Terminology Tables](#1-build-terminology-tables)
  - [2. Mapping Approaches](#2-mapping-approaches)
    - [2.1 Offline TSV (lexical)](#21-offline-tsv-lexical)
    - [2.2 Datasette keyword search](#22-datasette-keyword-search)
    - [2.3 Embedding re-ranking](#23-embedding-re-ranking)
    - [2.4 LLM-assisted mapping](#24-llm-assisted-mapping)
  - [3. Evaluate SSSOM outputs](#3-evaluate-sssom-outputs)
- [SemSynth CLI integration](#semsynth-cli-integration)

## Scripts Overview

1. `build_snomed_loinc_codes_table.py` – Build a TSV containing SNOMED CT and
   LOINC codes.
2. `build_wikidata_medical_codes_table.py` – Extract medical terminology from
   Wikidata into `codes.tsv`.
3. `codes_map_columns.py` – Perform offline lexical matching between dataset
   columns and entries in `codes.tsv`.
4. `kwd_map_columns.py` – Query a Datasette instance and apply lexical scoring
   to rank results.
5. `embed_map_columns.py` – Re-rank terminology candidates by combining
   sentence-transformer cosine similarity with lexical overlap diagnostics.
6. `llm_map_columns.py` – Orchestrate an LLM with Datasette tool access to
   obtain curated mappings.
7. `evaluate.py` – Compute micro/macro precision/recall/F1, MAP, and nDCG for
   SSSOM TSV files against a gold standard.

## Prerequisites

Install the baseline dependencies:

```bash
pip install defopt requests pandas numpy
```

Optional extras:

- Datasette helpers: `pip install datasette sqlite-utils llm-tools-datasette`
- Embedding re-ranking: `pip install sentence-transformers torch`
- LLM orchestration: `pip install llm`
- Evaluation: no additional packages beyond the baseline list

## Usage

### 1. Build Terminology Tables

#### Option A: SNOMED + LOINC

```bash
python build_snomed_loinc_codes_table.py \
    --snomed-description /path/to/Snapshot/Terminology/sct2_Description_Snapshot-en_INT_*.txt \
    --loinc /path/to/Loinc.csv \
    --out codes.tsv \
    --max-snomed 50000
```

#### Option B: Wikidata snapshot

```bash
python build_wikidata_medical_codes_table.py
```

After generating `codes.tsv`, you can load it into a SQLite / Datasette friendly
database:

```bash
sqlite-utils insert terminology.db codes codes.tsv --tsv
sqlite-utils enable-fts terminology.db codes label synonyms --create-triggers
```

### 2. Mapping Approaches

#### 2.1 Offline TSV (lexical)

```bash
python -m map_columns.codes_map_columns \
    dataset.semmap.json \
    --codes-tsv map_columns/codes.tsv \
    --manual-overrides map_columns/manual/uciml-145.json \
    --output-tsv mappings/uciml-145.sssom.tsv \
    --verbose
```

This mode keeps everything offline by comparing dataset metadata with the
synonyms contained in `codes.tsv`. Optional manual overrides provide exact
matches when lexical scoring is insufficient.

#### 2.2 Datasette keyword search

```bash
python map_columns/kwd_map_columns.py dataset.json \
    --datasette-db-url http://127.0.0.1:8001/terminology \
    --table codes \
    --limit 10 \
    --lexical-threshold 0.3 \
    --top-k 3 \
    --output mappings/uciml-145.keyword.sssom.tsv
```

The script requests candidate rows from Datasette, re-scores them with lexical
overlap, and emits SSSOM TSV rows. Results can be redirected to stdout by
omitting `--output`.

#### 2.3 Embedding re-ranking

```bash
python map_columns/embed_map_columns.py dataset.json \
    map_columns/codes.tsv \
    --model-name sentence-transformers/all-MiniLM-L6-v2 \
    --top-k 5 \
    --cosine-threshold 0.25 \
    --lexical-threshold 0.25 \
    --output mappings/uciml-145.embed.sssom.tsv
```

Candidates are first retrieved by lexical similarity and then re-ranked using a
sentence-transformer model. The exported TSV includes both lexical and cosine
diagnostics in the comments.

#### 2.4 LLM-assisted mapping

```bash
python map_columns/llm_map_columns.py dataset.json \
    --datasette-url http://127.0.0.1:8001/terminology \
    --model gpt-4.1-mini \
    --top-k 3 \
    --confidence-threshold 0.5 \
    --output mappings/uciml-145.llm.sssom.tsv
```

The LLM uses the Datasette tool to inspect code candidates and emits SSSOM rows
directly. Use `--extra-prompt` to provide project-specific guidance.

### 3. Evaluate SSSOM outputs

```bash
python map_columns/evaluate.py \
    gold/uciml-145.gold.sssom.tsv \
    --predictions mappings/uciml-145.sssom.tsv mappings/uciml-145.embed.sssom.tsv \
    --output eval/uciml-145.json
```

Metrics (micro/macro P/R/F1, MAP, nDCG) are printed for each prediction file.
When `--output` is supplied, the metrics are also written to a JSON report.

## SemSynth CLI integration

The end-to-end workflow can be launched via the SemSynth CLI. All mapping
strategies are now available under a single command:

```bash
python -m semsynth create-mapping uciml \
    --datasets 145 \
    --method embed \
    --codes-tsv map_columns/codes.tsv \
    --datasette-url http://127.0.0.1:8001/terminology \
    --lexical-threshold 0.25 \
    --top-k 3 \
    --outdir mappings/
```

Key flags:

- `--method`: `lexical` (default), `keyword`, `embed`, or `llm`
- Datasette-backed methods honour `--datasette-url`, `--datasette-table`, and
  `--datasette-limit`
- Embedding mode accepts `--embed-model`, `--candidate-pool-multiplier`, and
  `--cosine-threshold`
- LLM mode exposes `--llm-model`, `--llm-extra-prompt`, `--llm-subject-prefix`,
  and `--confidence-threshold`

Manual overrides continue to be respected. When overrides exist for a column,
the CLI replaces any automatically generated matches with the curated entries.

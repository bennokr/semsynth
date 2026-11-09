from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from .specs import DatasetSpec

LOGGER = logging.getLogger(__name__)


def _mappings_dir() -> Path:
    """Return directory containing curated mapping files."""

    repo_root = Path(__file__).resolve().parent.parent
    return repo_root / "mappings"


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def resolve_mapping_json(dataset_spec: DatasetSpec) -> Path | None:
    """Return the curated JSON-LD mapping path for the dataset if it exists."""
    mappings_dir = _mappings_dir()
    candidates = []

    provider = dataset_spec.provider
    provider_id = dataset_spec.id
    dataset_name = dataset_spec.name

    provider_norm = (
        provider.lower().strip()
        if isinstance(provider, str) and provider.strip()
        else None
    )
    if provider_norm and provider_norm not in {"openml", "uciml"}:
        provider_norm = _slugify(provider_norm)
    elif provider_norm:
        provider_norm = provider_norm

    if provider_norm and provider_id is not None:
        candidates.append(mappings_dir / f"{provider_norm}-{provider_id}.metadata.json")

    if provider_norm and isinstance(dataset_name, str) and dataset_name.strip():
        candidates.append(
            mappings_dir / f"{provider_norm}-{_slugify(dataset_name)}.metadata.json"
        )

    if isinstance(dataset_name, str) and dataset_name.strip():
        candidates.append(mappings_dir / f"{_slugify(dataset_name)}.metadata.json")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_mapping_json(path: Path) -> dict[str, Any]:
    """Load a curated codebook: DSV JSON-LD written by linked-codebook, with roles."""
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Mapping JSON must be an object")

    return data


def _dataset_slug(spec: DatasetSpec, label: str) -> str:
    """The file stem of a dataset's mappings: provider and id, or provider and the slugged name."""

    tail = str(spec.id) if spec.id is not None else _slugify(label)
    return "-".join(part for part in (spec.provider, tail) if part)


def _override_file(directory: Path | None, spec: DatasetSpec, slug: str) -> Path | None:
    """The manual override file of a dataset in ``directory``, if there is one."""

    if directory is None:
        return None
    names = [f"{slug}.json"]
    if spec.id is not None:
        names.append(f"{spec.provider}-{spec.id}.json")
    return next((path for name in names if (path := directory / name).exists()), None)


def _codebook_document(payload: Any, slug: str) -> dict[str, Any]:
    """The codebook of a loaded dataset as a JSON-LD document."""

    from .codebook import Codebook

    document = payload.metadata or payload.spec.meta
    if isinstance(document, Codebook):
        document = document.to_jsonld()
    if not isinstance(document, dict):
        raise RuntimeError(f"No metadata found for dataset {slug}")
    return document


def create_mappings(
    provider: str,
    *,
    datasets: list[str] | None = None,
    codes_tsv: str = "map_columns/codes.tsv",
    manual_overrides_dir: str | None = None,
    outdir: str | Path = "mappings/",
    indent: int = 2,
    version_tag: str = "",
    method: str = "lexical",
    **match_options: Any,
) -> list[Path]:
    """Create SSSOM mappings for datasets and merge them into their codebooks.

    Args:
        provider: ``"uciml"`` or ``"openml"``.
        datasets: Dataset identifiers; the provider's defaults when omitted.
        codes_tsv: Terminology TSV built by ``entailmap.match.build_wikidata_medical_codes_table``.
        manual_overrides_dir: Directory with optional ``<slug>.json`` overrides.
        outdir: Where the SSSOM files and the merged codebooks are written.
        indent: JSON indentation of the codebooks.
        version_tag: Version recorded in the SSSOM header.
        method: ``"lexical"``, ``"keyword"``, ``"embed"`` or ``"llm"``.
        **match_options: Further settings of ``entailmap.match.api.run_match`` (``systems``, ``min_score``,
            ``top_k``, the Datasette, embedding and LLM options).

    Returns:
        The paths of the SSSOM files written.

    Raises:
        ImportError: If ``entailmap.match`` is missing (extra ``mapping``).
        ValueError: If the matching method or its options are invalid.
    """

    try:
        from entailmap.match.api import run_match
        from entailmap.match.codes_map_columns import load_manual_overrides, write_sssom
        from entailmap.match.shared import parse_columns
    except ImportError as exc:
        raise ImportError("create_mappings needs entailmap.match: `pip install 'semsynth[mapping]'`.") from exc

    from .datasets import load_dataset, specs_from_input

    overrides_dir = Path(manual_overrides_dir) if manual_overrides_dir else None
    target = Path(outdir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for spec in specs_from_input(provider=provider, datasets=datasets):
        payload = load_dataset(spec)
        slug = _dataset_slug(spec, payload.spec.name or str(payload.spec.id))
        document = _codebook_document(payload, slug)
        columns, dataset_meta = parse_columns(document)
        matches = run_match(
            columns,
            dataset_meta,
            method=method,
            codes_tsv=codes_tsv,
            overrides=load_manual_overrides(_override_file(overrides_dir, spec, slug)),
            **match_options,
        )
        sssom_path = target / f"{slug}.sssom.tsv"
        write_sssom(matches, sssom_path, dataset_meta=dataset_meta, version_tag=version_tag)
        _merge_into_codebook(document, matches, target / f"{slug}.metadata.json", method, indent)
        LOGGER.info("Wrote mappings for %s -> %s", slug, sssom_path)
        written.append(sssom_path)
    return written


def _merge_into_codebook(document: dict[str, Any], matches: list[Any], path: Path, method: str, indent: int) -> None:
    """Integrate the matches into the codebook and write it as JSON-LD."""

    from .codebook import Codebook
    from .sssom_codebook import integrate_sssom

    updated = integrate_sssom(
        Codebook.read(document),
        [match.to_sssom_row() for match in matches],
        reviewer=f"semsynth map-columns ({method.lower()})",
    )
    path.write_text(json.dumps(updated.to_jsonld(), indent=indent, ensure_ascii=False), encoding="utf-8")

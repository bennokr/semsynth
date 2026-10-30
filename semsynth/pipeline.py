"""Pipeline orchestration for dataset processing and reporting."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields, is_dataclass
import re
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Set

import pandas as pd
from makeprov import OutDir, OutPath, rule, span
from makeprov.config import Config

from .backends.base import BackendModule, ensure_backend_contract
from .mappings import load_mapping_json, resolve_mapping_json
from .metadata import get_uciml_variable_descriptions
from .models import ModelConfigBundle, discover_model_runs, load_model_configs
from .runtime import DEPENDENCIES
from .specs import DatasetSpec
from .codebook import Codebook, privacy_role

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .missingness import DataFrameMissingnessModel


_BACKEND_MODULE_PATHS = {
    "pybnesian": "semsynth.backends.pybnesian",
    "synthcity": "semsynth.backends.synthcity",
    "metasyn": "semsynth.backends.metasyn",
}

@dataclass
class UmapConfig(Config):
    """UMAP geometry parameters."""

    n_neighbors: int = 30
    min_dist: float = 0.1
    n_components: int = 2


@dataclass
class PipelineConfig(Config):
    """Configuration values controlling the reporting pipeline."""

    random_state: int = 42
    max_umap_sample: int = 1000
    fit_on_sample: Optional[int] = 1000
    synthetic_sample: int = 1000
    test_size: float = 0.2
    umap: UmapConfig = field(default_factory=UmapConfig)
    generate_umap: bool = True
    compute_privacy: bool = False
    compute_downstream: bool = False
    overwrite_umap: bool = False
    enable_missingness_wrapping: bool = False
    missingness_random_state: Optional[int] = None

    def apply_mapping(self, params: Mapping[str, Any]) -> "PipelineConfig":
        """Apply a mapping of overrides onto this config, recursing into nested dataclasses."""

        if not isinstance(params, Mapping):
            return self

        def set_conf(dc: Any, mapping: Mapping[str, Any]) -> None:
            field_names = {f.name for f in fields(dc)}
            for key, value in mapping.items():
                if key not in field_names:
                    continue
                current = getattr(dc, key)
                if is_dataclass(current) and isinstance(value, Mapping):
                    set_conf(current, value)
                else:
                    setattr(dc, key, value)

        set_conf(self, params)
        return self


def _load_backend_module(name: str) -> BackendModule:
    module_path = _BACKEND_MODULE_PATHS.get(name)
    if not module_path:
        raise ValueError(f"Unknown backend '{name}'")
    module = DEPENDENCIES.require_module(
        module_path,
        hint=f"Install with `pip install semsynth[{name}]`.",
    )
    ensure_backend_contract(module)
    return module  # type: ignore[return-value]


def _build_privacy_metadata(
    df: "pd.DataFrame",
    inferred: Dict[str, str],
    *,
    metadata: Optional[Any] = None,
    role_overrides: Optional[Dict[str, str]] = None,
    target: Optional[str] = None,
) -> "pd.DataFrame":
    import pandas as pd

    metadata_df: Optional["pd.DataFrame"] = None
    try:
        codebook = Codebook.read(metadata) if metadata is not None else Codebook.from_frame(df)
        metadata_df = codebook.privacy_frame(inferred) if codebook.columns else None
    except Exception:
        LOGGER.exception("Failed to read metadata for privacy roles")
        metadata_df = None

    if metadata_df is None:
        rows = []
        for column, kind in inferred.items():
            dtype = "numeric" if kind == "continuous" else "categorical"
            rows.append({"variable": column, "role": "qi", "type": dtype})
        metadata_df = pd.DataFrame(rows)

    if role_overrides:
        for column, raw_role in role_overrides.items():
            normalized = privacy_role(raw_role)
            if column in metadata_df.variable.values:
                metadata_df.loc[metadata_df.variable == column, "role"] = normalized

    if target:
        target_mask = metadata_df.variable == target
        if target_mask.any():
            metadata_df.loc[target_mask, "role"] = "target"
        elif target in df.columns:
            kind = inferred.get(target, "continuous")
            dtype = "numeric" if kind == "continuous" else "categorical"
            metadata_df = pd.concat(
                [metadata_df, pd.DataFrame([{"variable": target, "role": "target", "type": dtype}])]
            )

    return metadata_df


def _build_downstream_meta(
    df: "pd.DataFrame",
    inferred: Dict[str, str],
    target_series: Optional["pd.Series"],
    *,
    target: Optional[str] = None,
) -> Codebook:
    """A codebook for downstream metrics when there is no metadata: levels from ``inferred`` and the target role."""
    import pandas as pd

    target_name: Optional[str] = None
    if isinstance(target_series, pd.Series):
        if target_series.attrs.get("prov:hadRole") == "target":
            target_name = target_series.name if target_series.name in df.columns else None
    if target_name is None and target and target in df.columns:
        target_name = target

    columns: List[Dict[str, Any]] = []
    for column in df.columns:
        if inferred.get(column, "continuous") == "continuous":
            columns.append({"name": str(column), "level": "numerical"})
            continue
        categories = [str(cat) for cat in df[column].astype("category").cat.categories]
        entry: Dict[str, Any] = {"name": str(column), "level": "nominal"}
        if categories:
            entry["values"] = [{"code": cat} for cat in categories]
        columns.append(entry)
    roles = {str(name): "target" if name == target_name else "predictor" for name in df.columns}
    return Codebook({"columns": columns}, roles)  # type: ignore[arg-type]


@dataclass
class UmapArtifacts:
    """Artifacts produced when UMAP visualisations are generated."""

    transformer: Any
    real_png: Path
    limits: Optional[Any]


@dataclass
class PreprocessingResult:
    """Result values produced by :class:`DatasetPreprocessor`."""

    df_processed: "pd.DataFrame"
    df_no_na: "pd.DataFrame"
    df_fit_sample: "pd.DataFrame"
    disc_cols: List[str]
    cont_cols: List[str]
    inferred_types: Dict[str, str]
    codebook_jsonld: Optional[Dict[str, Any]] = None
    codebook: Optional[Codebook] = None
    color_series: Optional["pd.Series"] = None
    umap_png_real: Optional[Path] = None
    umap_artifacts: Optional[UmapArtifacts] = None
    missingness_model: Optional["DataFrameMissingnessModel"] = None


class DatasetPreprocessor:
    """Prepare dataset inputs prior to backend execution."""

    def __init__(
        self,
        *,
        utils_module: Any,
        load_mapping: Any,
        resolve_mapping: Any,
    ) -> None:
        self._utils = utils_module
        self._load_mapping = load_mapping
        self._resolve_mapping = resolve_mapping

    @rule(phony=True)
    def preprocess(
        self,
        dataset_spec: "DatasetSpec",
        df: "pd.DataFrame",
        color_series: Optional["pd.Series"],
        outdir: OutPath,
        cfg: PipelineConfig,
        rng: Any,
        *,
        generate_umap: bool,
        umap_utils: Optional[Any],
    ) -> PreprocessingResult:
        """Clean data, apply metadata and optionally prepare UMAP artifacts.

        Args:
            dataset_spec: Dataset description metadata.
            df: Input dataframe to process.
            color_series: Optional colour labels for UMAP plots.
            outdir: Directory where artefacts should be stored.
            cfg: Active pipeline configuration.
            rng: Random state helper returned by ``utils.seed_all``.
            generate_umap: Whether to build UMAP artefacts.
            umap_utils: Module implementing UMAP helper routines.

        Returns:
            PreprocessingResult: Structured container with processed dataset
            artefacts used by later pipeline stages.
        """

        import pandas as pd

        self._utils.ensure_dir(str(outdir))

        logging.info(str(cfg))

        declared = Codebook()
        if dataset_spec.meta is not None:
            try:
                declared = Codebook.read(dataset_spec.meta)
            except Exception:
                LOGGER.exception(
                    "Failed to read dataset_spec metadata",
                    exc_info=True,
                    extra={"dataset": dataset_spec.name},
                )
        mapping_path = self._resolve_mapping(dataset_spec)
        if mapping_path is not None:
            LOGGER.info(
                "Applying curated codebook",
                extra={"dataset": dataset_spec.name, "mapping_path": str(mapping_path)},
            )
            try:
                declared = declared.merged(Codebook.read(self._load_mapping(mapping_path)))
            except Exception:
                LOGGER.exception(
                    "Failed to apply curated codebook",
                    exc_info=True,
                    extra={"dataset": dataset_spec.name},
                )
        codebook = Codebook.from_frame(df, declared)
        metadata_discrete: Set[str] = {name for name in df.columns if codebook.kind(str(name)) == "categorical"}
        metadata_continuous: Set[str] = {name for name in df.columns if codebook.kind(str(name)) == "numeric"}

        disc_cols, cont_cols = self._utils.infer_types(df)
        disc_set: Set[str] = set(disc_cols)
        cont_set: Set[str] = set(cont_cols)
        disc_set |= metadata_discrete
        cont_set |= {name for name in metadata_continuous if name not in disc_set}
        # Remove any lingering overlaps while preferring discrete assignments.
        for name in list(cont_set):
            if name in disc_set and name not in metadata_continuous:
                cont_set.discard(name)
        column_order = list(df.columns)
        disc_cols = [col for col in column_order if col in disc_set]
        cont_cols = [col for col in column_order if col in cont_set]
        df_processed = self._utils.coerce_discrete_to_category(df, disc_cols)
        df_processed = self._utils.rename_categorical_categories_to_str(
            df_processed, disc_cols
        )
        df_processed = self._utils.coerce_continuous_to_float(df_processed, cont_cols)

        inferred_map = {
            column: ("discrete" if column in disc_cols else "continuous")
            for column in df_processed.columns
        }

        df_no_na = df_processed.dropna(axis=0, how="any").reset_index(drop=True)
        if df_no_na.empty:
            df_no_na = df_processed.ffill().bfill().reset_index(drop=True)

        color_series2 = None
        target_column = dataset_spec.target
        if isinstance(color_series, pd.Series) and color_series.name in df_no_na.columns:
            color_series2 = df_no_na[color_series.name].copy()
            color_series2.attrs.update(color_series.attrs)
            if target_column and color_series2.attrs.get("prov:hadRole") != "target":
                color_series2.attrs["prov:hadRole"] = "target"
                target_column = color_series2.name
        if color_series2 is None and target_column and target_column in df_no_na.columns:
            color_series2 = df_no_na[target_column].copy()
            color_series2.attrs["prov:hadRole"] = "target"

        umap_png_real: Optional[Path] = outdir / "umap_real.png"
        umap_artifacts: Optional[UmapArtifacts] = None
        if generate_umap and umap_utils is not None:
            LOGGER.info(
                "Fitting UMAP on real data sample",
                extra={"dataset": dataset_spec.name},
            )
            try:
                umap_art = umap_utils.build_umap(
                    df_no_na,
                    disc_cols,
                    cont_cols,
                    color_series=color_series2,
                    rng=rng,
                    random_state=cfg.random_state,
                    max_sample=cfg.max_umap_sample,
                    n_neighbors=cfg.umap.n_neighbors,
                    min_dist=cfg.umap.min_dist,
                    n_components=cfg.umap.n_components,
                )
                umap_lims = umap_utils.plot_umap(
                    umap_art.embedding,
                    str(umap_png_real),
                    title=f"{dataset_spec.name}: real (sample)",
                    color_labels=umap_art.color_labels,
                )
            except RuntimeError as exc:
                LOGGER.warning(
                    "Skipping UMAP generation: %s",
                    exc,
                    extra={"dataset": dataset_spec.name},
                )
                umap_png_real = None
            except Exception:
                LOGGER.exception(
                    "UMAP generation failed",
                    extra={"dataset": dataset_spec.name},
                )
                umap_png_real = None
            else:
                umap_artifacts = UmapArtifacts(
                    transformer=umap_art, real_png=umap_png_real, limits=umap_lims
                )
        elif umap_png_real is not None and not umap_png_real.exists():
            umap_png_real = None

        df_fit_sample = df_no_na
        if cfg.fit_on_sample and cfg.fit_on_sample < len(df_fit_sample):
            df_fit_sample = df_no_na.sample(
                cfg.fit_on_sample, random_state=cfg.random_state
            )

        missingness_model: Optional["DataFrameMissingnessModel"] = None
        if cfg.enable_missingness_wrapping:
            miss_state = cfg.missingness_random_state
            if miss_state is None:
                miss_state = cfg.random_state
            try:
                from . import missingness as missingness_module
            except ImportError:
                LOGGER.warning(
                    "Missingness wrapping requested but dependencies are unavailable",
                    extra={"dataset": dataset_spec.name},
                )
            else:
                missingness_model = missingness_module.fit_missingness_model(
                    df_processed, random_state=miss_state
                )

        if target_column and target_column in df_processed.columns:
            codebook.roles[str(target_column)] = "target"
        codebook.set_statistics(df_processed, missingness_model)
        if "identifier" not in codebook.profile:
            label = dataset_spec.name or str(dataset_spec.id)
            slug = re.sub(r"[^a-z0-9]+", "-", str(label).lower()).strip("-") or "dataset"
            codebook.profile["identifier"] = f"urn:dataset:{slug}"
        if dataset_spec.name and "title" not in codebook.profile:
            codebook.profile["title"] = dataset_spec.name
        codebook_jsonld = codebook.to_jsonld()

        return PreprocessingResult(
            df_processed=df_processed,
            df_no_na=df_no_na,
            df_fit_sample=df_fit_sample,
            disc_cols=disc_cols,
            cont_cols=cont_cols,
            inferred_types=inferred_map,
            codebook_jsonld=codebook_jsonld,
            codebook=codebook,
            color_series=color_series2,
            umap_png_real=umap_png_real,
            umap_artifacts=umap_artifacts,
            missingness_model=missingness_model,
        )


class MetricWriter:
    """Persist privacy and downstream metrics for backend runs."""

    def __init__(
        self,
        *,
        privacy_summarizer: Optional[Any] = None,
        downstream_compare: Optional[Any] = None,
    ) -> None:
        self._privacy_summarizer = privacy_summarizer
        self._downstream_compare = downstream_compare

    @rule(phony=True)
    def write_privacy(
        self,
        run_dir: OutPath,
        real_df: "pd.DataFrame",
        inferred: Dict[str, str],
        synth_df: Optional["pd.DataFrame"] = None,
        metadata: Optional[Codebook] = None,
        *,
        role_overrides: Optional[Dict[str, str]] = None,
        target: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Write privacy metrics to disk for a backend run.

        Args:
            run_dir: Directory containing backend outputs.
            real_df: Real dataset without missing values.
            inferred: Mapping of column names to inferred types.
            synth_df: Optional synthetic dataframe to reuse.

        Returns:
            Dict[str, Any]: Serialized payload written to disk.
        """

        summarizer = self._privacy_summarizer or DEPENDENCIES.require_attr(
            "semsynth.privacy_metrics",
            "summarize_privacy_synthcity",
            hint="Install SemSynth with `synthcity` extras: `pip install semsynth[synthcity]`.",
        )

        if synth_df is None:
            synth_df = self._read_synthetic_df(run_dir)
        metadata_df = (
            metadata.privacy_frame(inferred)
            if isinstance(metadata, Codebook)
            else _build_privacy_metadata(
                real_df,
                inferred,
                metadata=metadata,
                role_overrides=role_overrides,
                target=target,
            )
        )
        if target and target in metadata_df.variable.values:
            metadata_df.loc[metadata_df.variable == target, "role"] = "target"
        summary = summarizer(real_df, synth_df, metadata_df)
        run_dir_path = Path(run_dir)
        run_dir_path.mkdir(parents=True, exist_ok=True)
        if is_dataclass(summary):
            payload = asdict(summary)
        elif isinstance(summary, Mapping):
            payload = dict(summary)
        else:
            payload = summary
        (run_dir / "metrics.privacy.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        return payload

    @rule(phony=True)
    def write_downstream(
        self,
        run_dir: OutPath,
        real_df: "pd.DataFrame",
        synth_df: "pd.DataFrame",
        inferred: Dict[str, str],
        target_series: Optional["pd.Series"],
        metadata: Optional[Codebook] = None,
        *,
        target: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Write downstream metrics comparing synthetic and real data.

        Args:
            run_dir: Directory containing backend outputs.
            real_df: Real dataset used for comparisons.
            synth_df: Synthetic dataset produced by backend.
            inferred: Mapping of column names to inferred types.
            target_series: Optional target series annotated with ``prov:hadRole``.

        Returns:
            Dict[str, Any]: Serialized payload written to disk.
        """

        comparer = self._downstream_compare or DEPENDENCIES.require_attr(
            "semsynth.downstream_fidelity",
            "compute_downstream",
            hint="Install downstream fidelity extras: `pip install semsynth[statsmodels]`.",
        )

        meta = metadata if isinstance(metadata, Codebook) else _build_downstream_meta(
            real_df, inferred, target_series, target=target
        )
        results = comparer(real_df, synth_df, meta)
        compare = results.get("compare")
        sign_match_rate = float("nan")
        if hasattr(compare, "__getitem__"):
            try:
                series = compare["sign_match"]  # type: ignore[index]
                sign_match_rate = float(series.astype(float).mean())
            except Exception:
                sign_match_rate = float("nan")
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        payload = {"formula": results.get("formula"), "sign_match_rate": sign_match_rate}
        (run_dir / "metrics.downstream.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        return payload

    @staticmethod
    def _read_synthetic_df(run_dir: Path) -> "pd.DataFrame":
        import pandas as pd

        return pd.read_csv(run_dir / "synthetic.csv").convert_dtypes()


class BackendExecutor:
    """Execute backend configurations and evaluate resulting data."""

    def __init__(
        self,
        cfg: PipelineConfig,
        *,
        load_backend: Any,
        metric_writer: MetricWriter,
    ) -> None:
        self._cfg = cfg
        self._load_backend = load_backend
        self._metric_writer = metric_writer

    @rule(phony=True)
    def run_models(
        self,
        dataset_spec: "DatasetSpec",
        bundle: ModelConfigBundle,
        preprocessed: PreprocessingResult,
        outdir: OutDir,
    ) -> None:
        """Execute each model specification and compute metrics if requested.

        Args:
            dataset_spec: Dataset metadata describing the run.
            bundle: Bundle of backend model configurations.
            preprocessed: Preprocessed dataset artefacts.
            outdir: Output directory for backend artefacts.
        """

        import pandas as pd

        outdir = outdir if isinstance(outdir, OutDir) else OutDir(outdir)
        outdir_path = Path(outdir)
        bundle_specs = bundle.specs if bundle.specs else []

        for idx, spec in enumerate(bundle_specs):
            label = spec.name or f"model_{idx + 1}"
            seed = int(spec.seed if spec.seed is not None else self._cfg.random_state)
            backend_name = spec.backend
            run_dir_path = outdir_path / "models" / label
            try:
                backend_module = self._load_backend(backend_name)
            except Exception:
                LOGGER.exception(
                    "Failed to load backend module",
                    extra={"backend": backend_name},
                )
                continue

            rows = spec.rows if spec.rows is not None else self._cfg.synthetic_sample
            with span(label, prov_path=run_dir_path / "provenance"):
                try:
                    run_dir = backend_module.run_experiment(
                        df=preprocessed.df_fit_sample,
                        provider=dataset_spec.provider,
                        dataset_name=dataset_spec.name,
                        provider_id=dataset_spec.id,
                        outdir=str(outdir_path),
                        label=label,
                        model_info=dict(spec.model or {}),
                        rows=min(rows, len(preprocessed.df_processed)),
                        seed=seed,
                        test_size=self._cfg.test_size,
                        codebook_jsonld=preprocessed.codebook_jsonld,
                    )
                except Exception:
                    LOGGER.exception(
                        "Backend run failed",
                        extra={"backend": backend_name, "label": label},
                    )
                    continue

                run_dir_path = Path(run_dir)
                synth_path = run_dir_path / "synthetic.csv"
                synth_df = pd.read_csv(synth_path).convert_dtypes()

                missingness_applied = False
                if preprocessed.missingness_model is not None:
                    try:
                        from . import missingness as missingness_module
                    except ImportError:
                        LOGGER.warning(
                            "Missingness wrapping requested but dependencies are unavailable",
                            extra={"label": label},
                        )
                    else:
                        synth_df, missingness_applied = (
                            missingness_module.apply_missingness_to_outputs(
                                run_dir=run_dir_path,
                                synth_df=synth_df,
                                missingness_model=preprocessed.missingness_model,
                                real_df=preprocessed.df_no_na,
                                disc_cols=preprocessed.disc_cols,
                                cont_cols=preprocessed.cont_cols,
                                backend_name=backend_name,
                            )
                        )

                compute_privacy_flag = self._cfg.compute_privacy
                if (
                    bundle.compute_privacy is not None
                    and bundle.compute_privacy != compute_privacy_flag
                ):
                    LOGGER.info(
                        "Ignoring bundle privacy flag in favour of pipeline configuration",
                        extra={
                            "label": label,
                            "bundle_value": bundle.compute_privacy,
                            "pipeline_value": compute_privacy_flag,
                        },
                    )
                if spec.compute_privacy is not None:
                    compute_privacy_flag = spec.compute_privacy

                compute_downstream_flag = self._cfg.compute_downstream
                if (
                    bundle.compute_downstream is not None
                    and bundle.compute_downstream != compute_downstream_flag
                ):
                    LOGGER.info(
                        "Ignoring bundle downstream flag in favour of pipeline configuration",
                        extra={
                            "label": label,
                            "bundle_value": bundle.compute_downstream,
                            "pipeline_value": compute_downstream_flag,
                        },
                    )
                if spec.compute_downstream is not None:
                    compute_downstream_flag = spec.compute_downstream

                if compute_privacy_flag:
                    try:
                        self._metric_writer.write_privacy(
                            run_dir_path,
                            preprocessed.df_no_na,
                            preprocessed.inferred_types,
                            synth_df,
                            preprocessed.codebook,
                            target=dataset_spec.target,
                        )
                        LOGGER.info(
                            "Wrote privacy metrics",
                            extra={"label": label},
                        )
                    except RuntimeError as exc:
                        LOGGER.warning(
                            "Privacy metrics unavailable; skipping: %s",
                            exc,
                            extra={"label": label},
                        )
                    except Exception:
                        LOGGER.exception(
                            "Failed to compute privacy metrics",
                            extra={"label": label},
                        )

                target_series = preprocessed.color_series
                has_target_series = (
                    isinstance(target_series, pd.Series)
                    and target_series.attrs.get("prov:hadRole") == "target"
                )
                if compute_downstream_flag and has_target_series:
                    try:
                        self._metric_writer.write_downstream(
                            run_dir_path,
                            preprocessed.df_no_na,
                            synth_df,
                            preprocessed.inferred_types,
                            target_series,
                            metadata=preprocessed.codebook,
                            target=dataset_spec.target,
                        )
                        LOGGER.info(
                            "Wrote downstream metrics",
                            extra={"label": label},
                        )
                    except RuntimeError as exc:
                        LOGGER.warning(
                            "Downstream metrics unavailable; skipping: %s",
                            exc,
                            extra={"label": label},
                        )
                    except Exception:
                        LOGGER.exception(
                            "Failed to compute downstream metrics",
                            extra={"label": label},
                        )

                try:
                    rel_root = run_dir_path.relative_to(outdir_path)
                except ValueError:
                    rel_root = Path("models") / label
                artifact_names = (
                    "synthetic.csv",
                    "per_variable_metrics.csv",
                    "metrics.json",
                    "metrics.privacy.json",
                    "metrics.downstream.json",
                    "umap.png",
                    "manifest.json",
                    "synthetic.parquet",
                    "metasyn_gmf.json",
                    "model.pickle",
                    "structure.graphml",
                    "structure.png",
                    "provenance.json",
                )
                for fname in artifact_names:
                    candidate = run_dir_path / fname
                    if candidate.exists():
                        outdir.file(rel_root / fname)


class ReportWriter:
    """Generate report outputs once backend runs are complete."""

    def __init__(self, reporting_module: Any, umap_utils: Optional[Any]) -> None:
        self._reporting = reporting_module
        self._umap_utils = umap_utils

    @rule(phony=True)
    def generate_synthetic_umaps(
        self,
        model_runs: Iterable[Any],
        dataset_spec: "DatasetSpec",
        preprocessed: PreprocessingResult,
        cfg: PipelineConfig,
    ) -> None:
        """Create UMAP visualisations for synthetic datasets if required.

        Args:
            model_runs: Iterable of discovered model run descriptors.
            dataset_spec: Dataset metadata describing the run.
            preprocessed: Preprocessed dataset artefacts.
            cfg: Pipeline configuration controlling thresholds.
        """

        if not self._umap_utils or not preprocessed.umap_artifacts:
            return

        for run in model_runs:
            try:
                if run.umap_png and run.umap_png.exists() and not cfg.overwrite_umap:
                    continue
                s_df = self._read_synthetic_df(run)
                if len(s_df) > cfg.max_umap_sample:
                    s_df = s_df.sample(cfg.max_umap_sample)
                s_df = s_df.reindex(columns=preprocessed.df_no_na.columns)
                s_emb = self._umap_utils.transform_with_umap(
                    preprocessed.umap_artifacts.transformer,
                    s_df.dropna(axis=0, how="any"),
                )
                run.umap_png = run.run_dir / "umap.png"
                self._umap_utils.plot_umap(
                    s_emb,
                    str(run.umap_png),
                    title=f"{dataset_spec.name}: synthetic ({run.name})",
                    lims=preprocessed.umap_artifacts.limits,
                )
            except Exception:
                LOGGER.exception(
                    "Failed to generate synthetic UMAP",
                    extra={"run_dir": str(run.run_dir)},
                )

    @staticmethod
    def _read_synthetic_df(run: Any) -> "pd.DataFrame":
        import pandas as pd

        return pd.read_csv(run.synthetic_csv).convert_dtypes()

    @rule(phony=True)
    def write_report(
        self,
        *,
        outdir: OutPath,
        dataset_spec: "DatasetSpec",
        preprocessed: PreprocessingResult,
        model_runs: List[Any],
        inferred_types: Optional[Dict[str, str]],
        variable_descriptions: Optional[Dict[str, Any]],
    ) -> None:
        """Persist the Markdown summary report.

        Args:
            outdir: Output directory for report artefacts.
            dataset_spec: Dataset metadata describing the run.
            preprocessed: Preprocessed dataset artefacts.
            model_runs: Collection of discovered model runs.
            inferred_types: Mapping of column names to inferred types.
            variable_descriptions: Optional variable description mapping.
        """

        try:
            from . import missingness as missingness_module
        except ImportError:
            missingness_summary = None
        else:
            missingness_summary = missingness_module.summarize_missingness_model(
                preprocessed.missingness_model
            )

        self._reporting.write_report_md(
            outdir=str(outdir),
            dataset_name=dataset_spec.name,
            dataset_provider=dataset_spec.provider,
            dataset_provider_id=dataset_spec.id,
            df=preprocessed.df_no_na,
            disc_cols=preprocessed.disc_cols,
            cont_cols=preprocessed.cont_cols,
            umap_png_real=str(preprocessed.umap_png_real)
            if preprocessed.umap_png_real
            else None,
            inferred_types=inferred_types or None,
            variable_descriptions=variable_descriptions or None,
            codebook_jsonld=preprocessed.codebook_jsonld,
            dataset_metadata=preprocessed.codebook,
            model_runs=model_runs,
            missingness_summary=missingness_summary,
        )

@rule(phony=True)
def process_dataset(
    dataset_spec: "DatasetSpec",
    df: "pd.DataFrame",
    color_series: Optional["pd.Series"],
    base_outdir: Path | OutPath | str,
    *,
    model_bundle: Optional[ModelConfigBundle] = None,
    pipeline_config: Optional[PipelineConfig] = None,
) -> None:
    """Process a dataset end-to-end and generate a report."""

    utils = DEPENDENCIES.require_module(
        "semsynth.utils",
        hint="Install SemSynth with base dependencies.",
    )
    reporting = DEPENDENCIES.require_module(
        "semsynth.reporting",
        hint="SemSynth reporting module missing. Reinstall package.",
    )

    bundle = model_bundle or load_model_configs(None)
    cfg = pipeline_config or PipelineConfig()

    base_path = Path(base_outdir)
    outdir = OutDir(base_path / dataset_spec.name.replace("/", "_"))
    rng = utils.seed_all(cfg.random_state)

    generate_umap_flag = cfg.generate_umap
    if bundle.generate_umap is not None:
        generate_umap_flag = bundle.generate_umap

    umap_utils = (
        DEPENDENCIES.require_module(
            "semsynth.umap_utils",
            hint="Install UMAP extras via `pip install semsynth[umap]`.",
        )
        if generate_umap_flag
        else None
    )

    preprocessor = DatasetPreprocessor(
        utils_module=utils,
        load_mapping=load_mapping_json,
        resolve_mapping=resolve_mapping_json,
    )
    preprocessed = preprocessor.preprocess(
        dataset_spec,
        df,
        color_series,
        outdir,
        cfg,
        rng,
        generate_umap=generate_umap_flag,
        umap_utils=umap_utils,
    )
    if preprocessed.codebook is not None:
        dataset_spec.meta = preprocessed.codebook

    privacy_summarizer = None
    downstream_compare = None
    if cfg.compute_privacy:
        try:
            privacy_summarizer = DEPENDENCIES.require_attr(
                "semsynth.privacy_metrics",
                "summarize_privacy_synthcity",
                hint="Install SemSynth with `synthcity` extras: `pip install semsynth[synthcity]`.",
            )
        except RuntimeError as exc:
            LOGGER.warning("Privacy metrics unavailable; disabling privacy computation: %s", exc)
            cfg.compute_privacy = False
    if cfg.compute_downstream:
        try:
            downstream_compare = DEPENDENCIES.require_attr(
                "semsynth.downstream_fidelity",
                "compute_downstream",
                hint="Install downstream fidelity extras: `pip install semsynth[statsmodels]`.",
            )
        except RuntimeError as exc:
            LOGGER.warning(
                "Downstream metrics unavailable; disabling downstream computation: %s", exc
            )
            cfg.compute_downstream = False

    metric_writer = MetricWriter(
        privacy_summarizer=privacy_summarizer,
        downstream_compare=downstream_compare,
    )
    executor = BackendExecutor(
        cfg,
        load_backend=_load_backend_module,
        metric_writer=metric_writer,
    )

    executor.run_models(dataset_spec, bundle, preprocessed, outdir)

    var_desc_map: Dict[str, Any] = {}
    if dataset_spec.provider == "uciml" and isinstance(dataset_spec.id, int):
        try:
            var_desc_map = get_uciml_variable_descriptions(dataset_spec.id)
        except Exception:
            var_desc_map = {}

    model_runs: List[Any] = []
    try:
        model_runs = discover_model_runs(outdir)
    except Exception:
        LOGGER.exception(
            "Failed to discover model runs",
            extra={"dataset": dataset_spec.name},
        )
        model_runs = []

    reporter = ReportWriter(reporting, umap_utils)
    reporter.generate_synthetic_umaps(model_runs, dataset_spec, preprocessed, cfg)
    reporter.write_report(
        outdir=outdir,
        dataset_spec=dataset_spec,
        preprocessed=preprocessed,
        model_runs=model_runs,
        inferred_types=preprocessed.inferred_types,
        variable_descriptions=var_desc_map,
    )

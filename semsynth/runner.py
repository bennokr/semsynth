"""Run the report pipeline on one dataset: preprocess, synthesize with each model, evaluate, write the files.

This module and :func:`semsynth.synthesis.write_run` are the only places of the pipeline that write files.
:func:`process_dataset` is the entry point; everything else is in :mod:`semsynth.preprocess`,
:mod:`semsynth.evaluate` and :mod:`semsynth.synthesis`, which work on tables in memory.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import PipelineConfig
from .evaluate import downstream_scores, holdout_metrics, privacy_scores, split_train_test
from .mappings import load_mapping_json, resolve_mapping_json
from .metadata import get_uciml_variable_descriptions
from .models import ModelConfigBundle, ModelSpec, discover_model_runs, load_model_configs
from .preprocess import DatasetPreprocessor, PreprocessingResult
from .result import SynthesisResult
from .specs import DatasetSpec
from .synthesis import EVALUATES_ITSELF, synthesize, write_run

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

LOGGER = logging.getLogger(__name__)

__all__ = ["BackendExecutor", "PipelineDeps", "ReportWriter", "plot_real_umap", "process_dataset"]


@dataclass
class PipelineDeps:
    """Replaceable collaborators of :func:`process_dataset`.

    Every field defaults to ``None``, which means "import the real one when it is needed". Tests and
    embedding applications pass their own objects instead of patching modules.
    """

    utils: Any | None = None
    reporting: Any | None = None
    umap_utils: Any | None = None
    privacy_summarizer: Any | None = None
    downstream_compare: Any | None = None
    synthesize: Any | None = None


def _resolve_flag(
    name: str, configured: bool, bundle_value: bool | None, spec_value: bool | None, label: str
) -> bool:
    """A model's metric flag: its own setting wins, then the pipeline configuration (the bundle's is ignored)."""

    if bundle_value is not None and bundle_value != configured:
        LOGGER.info(
            "Ignoring bundle %s flag in favour of pipeline configuration",
            name,
            extra={"label": label, "bundle_value": bundle_value, "pipeline_value": configured},
        )
    return configured if spec_value is None else spec_value


def _attempt(kind: str, label: str, compute: Any, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
    """Compute a metric; a missing extra or a failure is logged and does not stop the run."""

    try:
        payload: dict[str, Any] = compute(*args, **kwargs)
    except ImportError as exc:
        LOGGER.warning("%s metrics unavailable; skipping: %s", kind.capitalize(), exc, extra={"label": label})
    except Exception:
        LOGGER.exception("Failed to compute %s metrics", kind, extra={"label": label})
    else:
        LOGGER.info("Computed %s metrics", kind, extra={"label": label})
        return payload
    return None


class BackendExecutor:
    """Fit each model of a bundle, evaluate what it generates and write the run directories."""

    def __init__(
        self,
        cfg: PipelineConfig,
        *,
        synthesize_fn: Any | None = None,
        privacy_summarizer: Any | None = None,
        downstream_compare: Any | None = None,
    ) -> None:
        self._cfg = cfg
        self._synthesize = synthesize_fn or synthesize
        self._privacy_summarizer = privacy_summarizer
        self._downstream_compare = downstream_compare

    def run_models(
        self,
        dataset_spec: DatasetSpec,
        bundle: ModelConfigBundle,
        preprocessed: PreprocessingResult,
        outdir: str | Path,
    ) -> None:
        """Run each model specification, write ``models/<label>`` and compute metrics if requested.

        A model that fails is logged and skipped, so that the others still run.

        Args:
            dataset_spec: Dataset metadata describing the run.
            bundle: Bundle of model configurations.
            preprocessed: Preprocessed dataset artefacts.
            outdir: Output directory of the dataset.
        """

        for idx, spec in enumerate(bundle.specs or []):
            label = spec.name or f"model_{idx + 1}"
            try:
                self._run_spec(dataset_spec, bundle, spec, label, preprocessed, Path(outdir))
            except Exception:
                LOGGER.exception("Backend run failed", extra={"backend": spec.backend, "label": label})

    def _run_spec(
        self,
        dataset_spec: DatasetSpec,
        bundle: ModelConfigBundle,
        spec: ModelSpec,
        label: str,
        preprocessed: PreprocessingResult,
        outdir: Path,
    ) -> None:
        result = self._generate(spec, preprocessed)
        pristine = result.synthetic_data.convert_dtypes()
        final, metrics, parameters, artifacts = self._wrap_missingness(label, result, pristine, preprocessed)
        privacy_flag = _resolve_flag(
            "privacy", self._cfg.compute_privacy, bundle.compute_privacy, spec.compute_privacy, label
        )
        downstream_flag = _resolve_flag(
            "downstream", self._cfg.compute_downstream, bundle.compute_downstream, spec.compute_downstream, label
        )
        if privacy_flag:
            privacy = _attempt(
                "privacy", label, self._privacy, final, preprocessed, dataset_spec.target
            )
            if privacy is not None:
                metrics["privacy"] = privacy
        if downstream_flag and self._has_target(preprocessed):
            downstream = _attempt(
                "downstream", label, self._downstream, final, preprocessed, dataset_spec.target
            )
            if downstream is not None:
                metrics["downstream"] = downstream
        result = replace(
            result, synthetic_data=final, metrics=metrics, parameters=parameters, artifacts=artifacts
        )
        dataset = {
            "provider": dataset_spec.provider,
            "dataset_name": dataset_spec.name,
            "provider_id": dataset_spec.id,
        }
        write_run(
            result,
            outdir / "models" / label,
            label=label,
            dataset=dataset,
            codebook_jsonld=preprocessed.codebook_jsonld,
        )

    def _generate(self, spec: ModelSpec, preprocessed: PreprocessingResult) -> SynthesisResult:
        """Synthesize with one model and, unless the backend does it itself, evaluate on held-out rows."""

        cfg = self._cfg
        seed = int(spec.seed if spec.seed is not None else cfg.random_state)
        wanted = spec.rows if spec.rows is not None else cfg.synthetic_sample
        rows = min(wanted, len(preprocessed.df_processed))
        options = dict(spec.model or {})
        if spec.backend in EVALUATES_ITSELF:
            return self._synthesize(  # type: ignore[no-any-return]
                preprocessed.df_fit_sample,
                preprocessed.codebook,
                backend=spec.backend,
                rows=rows,
                seed=seed,
                **{**options, "test_size": cfg.test_size},
            )
        train, test = split_train_test(preprocessed.df_fit_sample, cfg.test_size, seed)
        result: SynthesisResult = self._synthesize(
            train, preprocessed.codebook, backend=spec.backend, rows=rows, seed=seed, **options
        )
        metrics = holdout_metrics(test, result.synthetic_data, preprocessed.disc_cols, preprocessed.cont_cols)
        return replace(
            result,
            metrics={**result.metrics, **metrics, "train_rows": len(train)},
            parameters={**result.parameters, "test_size": cfg.test_size},
        )

    @staticmethod
    def _wrap_missingness(
        label: str, result: SynthesisResult, pristine: pd.DataFrame, preprocessed: PreprocessingResult
    ) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any], dict[str, bytes | str]]:
        """Put the learned missingness into the synthetic table; the complete table is kept as an artifact."""

        metrics = dict(result.metrics)
        parameters = dict(result.parameters)
        artifacts = dict(result.artifacts)
        model = preprocessed.missingness_model
        if model is None:
            return pristine, metrics, parameters, artifacts
        from .missingness import apply_missingness, missingness_manifest

        try:
            wrapped, refreshed = apply_missingness(
                model, pristine, preprocessed.df_no_na, preprocessed.disc_cols, preprocessed.cont_cols
            )
        except Exception:
            LOGGER.exception("Failed to apply the missingness model", extra={"label": label})
            return pristine, metrics, parameters, artifacts
        artifacts["synthetic.nomissing.csv"] = pristine.to_csv(index=False)
        metrics.update(refreshed)
        parameters["missingness"] = missingness_manifest(model)
        return wrapped, metrics, parameters, artifacts

    def _privacy(self, synth_df: pd.DataFrame, preprocessed: PreprocessingResult, target: str | None) -> dict[str, Any]:
        return privacy_scores(
            preprocessed.df_no_na,
            synth_df,
            preprocessed.inferred_types,
            preprocessed.codebook,
            summarizer=self._privacy_summarizer,
            target=target,
        )

    def _downstream(
        self, synth_df: pd.DataFrame, preprocessed: PreprocessingResult, target: str | None
    ) -> dict[str, Any]:
        return downstream_scores(
            preprocessed.df_no_na,
            synth_df,
            preprocessed.inferred_types,
            preprocessed.color_series,
            preprocessed.codebook,
            compare=self._downstream_compare,
            target=target,
        )

    @staticmethod
    def _has_target(preprocessed: PreprocessingResult) -> bool:
        import pandas as pd

        series = preprocessed.color_series
        return isinstance(series, pd.Series) and series.attrs.get("prov:hadRole") == "target"


def plot_real_umap(
    preprocessed: PreprocessingResult,
    outdir: str | Path,
    dataset_spec: DatasetSpec,
    umap_utils: Any | None,
    *,
    generated: bool,
) -> None:
    """Draw the UMAP of the real data, or pick up the plot of an earlier run.

    Args:
        preprocessed: Result of preprocessing; its ``umap_artifacts`` and ``umap_png_real`` are completed.
        outdir: Output directory of the dataset.
        dataset_spec: Dataset metadata, for the title.
        umap_utils: Module implementing the UMAP helpers.
        generated: Whether UMAP was requested; if not, an existing ``umap_real.png`` is reused.
    """

    png = Path(outdir) / "umap_real.png"
    fitted = preprocessed.umap_artifacts
    if not generated:
        preprocessed.umap_png_real = png if png.exists() else None
        return
    if fitted is None or umap_utils is None:
        return
    try:
        fitted.limits = umap_utils.plot_umap(
            fitted.transformer.embedding,
            str(png),
            title=f"{dataset_spec.name}: real (sample)",
            color_labels=fitted.transformer.color_labels,
        )
    except ImportError as exc:
        LOGGER.warning("Skipping UMAP generation: %s", exc, extra={"dataset": dataset_spec.name})
    except Exception:
        LOGGER.exception("UMAP generation failed", extra={"dataset": dataset_spec.name})
    else:
        fitted.real_png = png
        preprocessed.umap_png_real = png
        return
    preprocessed.umap_artifacts = None


class ReportWriter:
    """Generate report outputs once backend runs are complete."""

    def __init__(self, reporting_module: Any, umap_utils: Any | None) -> None:
        self._reporting = reporting_module
        self._umap_utils = umap_utils

    def generate_synthetic_umaps(
        self,
        model_runs: Iterable[Any],
        dataset_spec: DatasetSpec,
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
                self._plot_synthetic(run, dataset_spec, preprocessed, cfg)
            except Exception:
                LOGGER.exception("Failed to generate synthetic UMAP", extra={"run_dir": str(run.run_dir)})

    def _plot_synthetic(
        self, run: Any, dataset_spec: DatasetSpec, preprocessed: PreprocessingResult, cfg: PipelineConfig
    ) -> None:
        import pandas as pd

        fitted = preprocessed.umap_artifacts
        assert fitted is not None
        synthetic = pd.read_csv(run.synthetic_csv).convert_dtypes()
        if len(synthetic) > cfg.max_umap_sample:
            synthetic = synthetic.sample(cfg.max_umap_sample)
        synthetic = synthetic.reindex(columns=preprocessed.df_no_na.columns)
        embedding = self._umap_utils.transform_with_umap(fitted.transformer, synthetic.dropna(axis=0, how="any"))
        run.umap_png = run.run_dir / "umap.png"
        self._umap_utils.plot_umap(
            embedding,
            str(run.umap_png),
            title=f"{dataset_spec.name}: synthetic ({run.name})",
            lims=fitted.limits,
        )

    def write_report(
        self,
        *,
        outdir: str | Path,
        dataset_spec: DatasetSpec,
        preprocessed: PreprocessingResult,
        model_runs: list[Any],
        inferred_types: dict[str, str] | None,
        variable_descriptions: dict[str, Any] | None,
    ) -> None:
        """Persist the Markdown and HTML summary report.

        Args:
            outdir: Output directory for report artefacts.
            dataset_spec: Dataset metadata describing the run.
            preprocessed: Preprocessed dataset artefacts.
            model_runs: Collection of discovered model runs.
            inferred_types: Mapping of column names to inferred types.
            variable_descriptions: Optional variable description mapping.
        """

        from .missingness import summarize_missingness_model

        self._reporting.write_report_md(
            outdir=str(outdir),
            dataset_name=dataset_spec.name,
            dataset_provider=dataset_spec.provider,
            dataset_provider_id=dataset_spec.id,
            df=preprocessed.df_no_na,
            disc_cols=preprocessed.disc_cols,
            cont_cols=preprocessed.cont_cols,
            umap_png_real=str(preprocessed.umap_png_real) if preprocessed.umap_png_real else None,
            inferred_types=inferred_types or None,
            variable_descriptions=variable_descriptions or None,
            codebook_jsonld=preprocessed.codebook_jsonld,
            dataset_metadata=preprocessed.codebook,
            model_runs=model_runs,
            missingness_summary=summarize_missingness_model(preprocessed.missingness_model),
        )


def _umap_module(deps: PipelineDeps, enabled: bool) -> Any | None:
    """The UMAP helpers: the injected module, or ``semsynth.umap_utils`` when UMAP is on."""

    if deps.umap_utils is not None or not enabled:
        return deps.umap_utils
    from . import umap_utils

    return umap_utils


def _variable_descriptions(dataset_spec: DatasetSpec) -> dict[str, Any]:
    if dataset_spec.provider == "uciml" and isinstance(dataset_spec.id, int):
        try:
            return get_uciml_variable_descriptions(dataset_spec.id)
        except Exception:
            return {}
    return {}


def _discover_runs(outdir: Path, dataset_spec: DatasetSpec) -> list[Any]:
    try:
        return discover_model_runs(outdir)
    except Exception:
        LOGGER.exception("Failed to discover model runs", extra={"dataset": dataset_spec.name})
        return []


def _preprocess(
    dataset_spec: DatasetSpec,
    df: pd.DataFrame,
    color_series: pd.Series | None,
    cfg: PipelineConfig,
    deps: PipelineDeps,
    umap_utils: Any | None,
    generate_umap: bool,
) -> PreprocessingResult:
    if deps.utils is None:
        from . import utils as utils_module
    else:
        utils_module = deps.utils
    preprocessor = DatasetPreprocessor(
        utils_module=utils_module,
        load_mapping=load_mapping_json,
        resolve_mapping=resolve_mapping_json,
    )
    return preprocessor.preprocess(
        dataset_spec,
        df,
        color_series,
        cfg,
        utils_module.seed_all(cfg.random_state),
        generate_umap=generate_umap,
        umap_utils=umap_utils,
    )


def process_dataset(
    dataset_spec: DatasetSpec,
    df: pd.DataFrame,
    color_series: pd.Series | None,
    base_outdir: str | Path,
    *,
    model_bundle: ModelConfigBundle | None = None,
    pipeline_config: PipelineConfig | None = None,
    deps: PipelineDeps | None = None,
) -> None:
    """Process a dataset end-to-end and generate a report under ``base_outdir/<dataset name>``.

    Args:
        dataset_spec: Where the dataset comes from, its name and its target.
        df: The table.
        color_series: Optional labels for the UMAP plots; the target column if omitted.
        base_outdir: Directory that gets one subdirectory per dataset.
        model_bundle: Models to run; none gives a metadata-only report.
        pipeline_config: Settings of the pipeline.
        deps: Replacements for the collaborators that are otherwise imported when needed.
    """

    deps = deps or PipelineDeps()
    bundle = model_bundle or load_model_configs(None)
    cfg = pipeline_config or PipelineConfig()
    outdir = Path(base_outdir) / str(dataset_spec.name).replace("/", "_")
    outdir.mkdir(parents=True, exist_ok=True)

    generate_umap = bundle.generate_umap if bundle.generate_umap is not None else cfg.generate_umap
    umap_utils = _umap_module(deps, generate_umap)
    preprocessed = _preprocess(dataset_spec, df, color_series, cfg, deps, umap_utils, generate_umap)
    plot_real_umap(preprocessed, outdir, dataset_spec, umap_utils, generated=generate_umap)
    if preprocessed.codebook is not None:
        dataset_spec.meta = preprocessed.codebook

    BackendExecutor(
        cfg,
        synthesize_fn=deps.synthesize,
        privacy_summarizer=deps.privacy_summarizer,
        downstream_compare=deps.downstream_compare,
    ).run_models(dataset_spec, bundle, preprocessed, outdir)

    model_runs = _discover_runs(outdir, dataset_spec)
    if deps.reporting is None:
        from . import reporting as reporting_module
    else:
        reporting_module = deps.reporting
    reporter = ReportWriter(reporting_module, umap_utils)
    reporter.generate_synthetic_umaps(model_runs, dataset_spec, preprocessed, cfg)
    reporter.write_report(
        outdir=outdir,
        dataset_spec=dataset_spec,
        preprocessed=preprocessed,
        model_runs=model_runs,
        inferred_types=preprocessed.inferred_types,
        variable_descriptions=_variable_descriptions(dataset_spec),
    )

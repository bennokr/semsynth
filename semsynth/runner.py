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

from .baselines import evaluate_references
from .config import PipelineConfig
from .crossval import fold_record, fold_splits, summarize_folds
from .evaluate import (
    downstream_scores,
    holdout_metrics,
    privacy_frame,
    privacy_scores,
    split_train_test,
)
from .iris import slug
from .mappings import load_mapping_json, resolve_mapping_json
from .metadata import get_uciml_variable_descriptions
from .models import ModelConfigBundle, ModelSpec, discover_model_runs, load_model_configs
from .preprocess import DatasetPreprocessor, PreprocessingResult
from .result import SynthesisResult
from .specs import DatasetSpec
from .synthesis import synthesize, write_run
from .utility import tstr_utility, utility_tables

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


def _attempt_record(kind: str, label: str, compute: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Like :func:`_attempt`, but a missing extra or a failure is returned as a ``status`` record, not dropped."""

    try:
        payload: dict[str, Any] = compute(*args, **kwargs)
    except ImportError as exc:
        LOGGER.warning("%s metrics unavailable; skipping: %s", kind.capitalize(), exc, extra={"label": label})
        return {"status": "skipped", "reason": str(exc)}
    except Exception as exc:
        LOGGER.exception("Failed to compute %s metrics", kind, extra={"label": label})
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
    return payload


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
        result, train, holdout, folds = self._generate(spec, preprocessed, dataset_spec.target)
        pristine = result.synthetic_data.convert_dtypes()
        final, metrics, parameters, artifacts = self._wrap_missingness(label, result, pristine, preprocessed)
        if self._cfg.structure_aware:
            final = self._enforce_rules(final, metrics, parameters, preprocessed)
        privacy_flag = _resolve_flag(
            "privacy", self._cfg.compute_privacy, bundle.compute_privacy, spec.compute_privacy, label
        )
        downstream_flag = _resolve_flag(
            "downstream", self._cfg.compute_downstream, bundle.compute_downstream, spec.compute_downstream, label
        )
        if privacy_flag:
            # The complete table, because the generator learned from complete rows; the released table with its
            # learned missingness is not evaluated yet.
            metrics["privacy"] = self._privacy(
                pristine, train, holdout, preprocessed, dataset_spec.target, int(spec.seed or self._cfg.random_state), label
            )
        if (
            self._cfg.compute_joint
            or self._cfg.compute_baselines
            or self._cfg.compute_subgroups
            or self._cfg.compute_utility
        ):
            self._add_evaluation(
                metrics,
                pristine,
                final,
                train,
                holdout,
                preprocessed,
                dataset_spec.target,
                spec,
                label,
            )
            if len(folds) > 1:
                metrics["cv"] = self._cross_validate(
                    folds, pristine, preprocessed, dataset_spec.target, spec, label
                )
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
            outdir / "models" / slug(label, "model"),
            label=label,
            dataset=dataset,
            codebook_jsonld=preprocessed.codebook_jsonld,
            base_iri=self._cfg.iri_base,
            parent_activity=self._cfg.parent_activity,
        )

    def _folds(
        self, preprocessed: PreprocessingResult, seed: int, target: str | None
    ) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
        """The (training, held-out) pairs: the folds of a cross-validation, or one split of ``test_size``."""

        cfg, frame = self._cfg, preprocessed.df_fit_sample
        if cfg.cv_folds < 2 or len(frame) < 2 * cfg.cv_folds:
            return [split_train_test(frame, cfg.test_size, seed)]
        discrete = (
            target in frame.columns and preprocessed.inferred_types.get(str(target)) == "discrete"
        )
        return fold_splits(frame, cfg.cv_folds, seed, frame[target] if discrete else None)

    def _generate(
        self, spec: ModelSpec, preprocessed: PreprocessingResult, target: str | None
    ) -> tuple[
        SynthesisResult, pd.DataFrame, pd.DataFrame, list[tuple[pd.DataFrame, pd.DataFrame]]
    ]:
        """Synthesize with one model and evaluate it on held-out rows.

        Returns the result, the training and the held-out rows of the first fold, and all the folds. The released table
        is the one of the first fold.
        """

        cfg = self._cfg
        seed = int(spec.seed if spec.seed is not None else cfg.random_state)
        wanted = spec.rows if spec.rows is not None else cfg.synthetic_sample
        rows = min(wanted, len(preprocessed.df_processed))
        options = dict(spec.model or {})
        folds = self._folds(preprocessed, seed, target)
        train, test = folds[0]
        result: SynthesisResult = self._synthesize(
            train, preprocessed.codebook, backend=spec.backend, rows=rows, seed=seed, **options
        )
        metrics = holdout_metrics(
            test,
            result.synthetic_data,
            preprocessed.disc_cols,
            preprocessed.cont_cols,
            model=result.learned_model,
            bootstrap_reps=cfg.bootstrap_reps,
            seed=seed,
        )
        result = replace(
            result,
            metrics={**result.metrics, **metrics, "train_rows": len(train)},
            parameters={
                **result.parameters,
                "test_size": cfg.test_size,
                "cv_folds": len(folds) if len(folds) > 1 else 1,
            },
        )
        return result, train, test, folds

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

    @staticmethod
    def _enforce_rules(
        final: pd.DataFrame, metrics: dict[str, Any], parameters: dict[str, Any], preprocessed: PreprocessingResult
    ) -> pd.DataFrame:
        """Empty the cells that the codebook's skip rules mark as not applicable, and record how many were filled."""

        from .structure import enforce_applicability, structural_violations

        violations = structural_violations(final, preprocessed.codebook)
        metrics["structure"] = {"violation_rate_before_rules": violations["rate"], "columns": violations["columns"]}
        parameters["structure_aware"] = True
        return enforce_applicability(final, preprocessed.codebook)

    def _privacy(
        self,
        synth_df: pd.DataFrame,
        train: pd.DataFrame,
        holdout: pd.DataFrame,
        preprocessed: PreprocessingResult,
        target: str | None,
        seed: int,
        label: str,
    ) -> dict[str, Any]:
        """Privacy scores, or a record of why there are none: a requested metric that is missing must show in the output."""

        try:
            scores = privacy_scores(
                train,
                synth_df,
                preprocessed.inferred_types,
                preprocessed.codebook,
                holdout_df=holdout,
                summarizer=self._privacy_summarizer,
                target=target,
                seed=seed,
                missing=self._cfg.privacy_missing,
                bootstrap_reps=self._cfg.bootstrap_reps,
            )
        except ImportError as exc:
            LOGGER.warning("Privacy metrics unavailable; skipping: %s", exc, extra={"label": label})
            return {"status": "skipped", "reason": str(exc)}
        except Exception as exc:
            LOGGER.exception("Failed to compute privacy metrics", extra={"label": label})
            return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
        LOGGER.info("Computed privacy metrics", extra={"label": label})
        return scores

    def _add_evaluation(
        self,
        metrics: dict[str, Any],
        pristine: pd.DataFrame,
        final: pd.DataFrame,
        train: pd.DataFrame,
        holdout: pd.DataFrame,
        preprocessed: PreprocessingResult,
        target: str | None,
        spec: ModelSpec,
        label: str,
    ) -> None:
        """Joint fidelity and the reference-table comparison, each recorded as failed rather than dropped."""

        cfg = self._cfg
        seed = int(spec.seed if spec.seed is not None else cfg.random_state)
        frame = privacy_frame(train, preprocessed.inferred_types, preprocessed.codebook, target=target)
        kinds = dict(zip(frame.variable, frame.type, strict=False))
        if cfg.compute_joint:
            metrics["joint"] = _attempt_record(
                "joint", label, self._joint, pristine, final, holdout, preprocessed, kinds, seed
            )
        if cfg.compute_utility:
            tables = utility_tables(train, pristine, seed)
            metrics["utility"] = _attempt_record(
                "utility",
                label,
                tstr_utility,
                train,
                holdout,
                tables,
                target,
                kinds,
                seed=seed,
                reps=cfg.bootstrap_reps,
            )
        if cfg.compute_subgroups:
            metrics["subgroups"] = _attempt_record(
                "subgroups", label, self._subgroups, pristine, train, holdout, preprocessed, frame, seed
            )
        if cfg.compute_baselines:
            metrics["baselines"] = _attempt_record(
                "baselines",
                label,
                evaluate_references,
                train,
                holdout,
                pristine,
                disc_cols=preprocessed.disc_cols,
                cont_cols=preprocessed.cont_cols,
                privacy_frame=frame,
                seed=seed,
                reps=cfg.bootstrap_reps,
                missing=cfg.privacy_missing,
            )

    def _cross_validate(
        self,
        folds: list[tuple[pd.DataFrame, pd.DataFrame]],
        pristine: pd.DataFrame,
        preprocessed: PreprocessingResult,
        target: str | None,
        spec: ModelSpec,
        label: str,
    ) -> dict[str, Any]:
        """Scores of every fold, with the mean and an interval over the folds.

        The first fold is the one that produced the released table. The others fit the same model on their own training
        rows, so the scores show how much they depend on which rows were learned from. A fold that fails is logged and
        left out.
        """

        cfg = self._cfg
        seed = int(spec.seed if spec.seed is not None else cfg.random_state)
        records = []
        for index, (train, test) in enumerate(folds):
            synthetic = pristine
            if index:
                try:
                    fitted = self._synthesize(
                        train,
                        preprocessed.codebook,
                        backend=spec.backend,
                        rows=len(pristine),
                        seed=seed + index,
                        **dict(spec.model or {}),
                    )
                except Exception:
                    LOGGER.exception(
                        "Cross-validation fold failed", extra={"label": label, "fold": index}
                    )
                    continue
                synthetic = fitted.synthetic_data.convert_dtypes()
            records.append(
                self._fold_record(train, test, synthetic, preprocessed, target, seed + index)
            )
        sizes = [(len(train), len(test)) for train, test in folds]
        return summarize_folds(
            records,
            round(sum(a for a, _ in sizes) / len(sizes)),
            round(sum(b for _, b in sizes) / len(sizes)),
        )

    def _fold_record(
        self,
        train: pd.DataFrame,
        test: pd.DataFrame,
        synthetic: pd.DataFrame,
        preprocessed: PreprocessingResult,
        target: str | None,
        seed: int,
    ) -> dict[str, dict[str, float]]:
        """The scalar scores of one fold: fidelity, joint fidelity and privacy for the table and its references, and utility."""

        cfg = self._cfg
        frame = privacy_frame(
            train, preprocessed.inferred_types, preprocessed.codebook, target=target
        )
        references = evaluate_references(
            train,
            test,
            synthetic,
            disc_cols=preprocessed.disc_cols,
            cont_cols=preprocessed.cont_cols,
            privacy_frame=frame,
            seed=seed,
            reps=0,
            missing=cfg.privacy_missing,
        )
        utility = None
        if cfg.compute_utility:
            kinds = dict(zip(frame.variable, frame.type, strict=False))
            tables = utility_tables(train, synthetic, seed)
            utility = _attempt_record(
                "utility", "fold", tstr_utility, train, test, tables, target, kinds, seed=seed
            )
        return fold_record(references, utility)

    def _subgroups(
        self,
        pristine: pd.DataFrame,
        train: pd.DataFrame,
        holdout: pd.DataFrame,
        preprocessed: PreprocessingResult,
        frame: pd.DataFrame,
        seed: int,
    ) -> dict[str, Any]:
        from .structure import check_subgroups, subgroups_from
        from .subgroups import subgroup_scores

        groups = subgroups_from(self._cfg.subgroups)
        problems = check_subgroups(groups, train.columns)
        if problems:
            raise ValueError("; ".join(problems))
        return subgroup_scores(
            train, holdout, pristine, groups, privacy_frame=frame, disc_cols=preprocessed.disc_cols,
            cont_cols=preprocessed.cont_cols, min_size=self._cfg.subgroup_min_size, seed=seed,
            reps=min(self._cfg.bootstrap_reps, 100), missing=self._cfg.privacy_missing,
        )

    def _joint(
        self,
        pristine: pd.DataFrame,
        final: pd.DataFrame,
        holdout: pd.DataFrame,
        preprocessed: PreprocessingResult,
        kinds: dict[str, str],
        seed: int,
    ) -> dict[str, Any]:
        from .joint_fidelity import joint_fidelity, missingness_fidelity

        scores = joint_fidelity(holdout, pristine, kinds, seed=seed, reps=min(self._cfg.bootstrap_reps, 50))
        if preprocessed.missingness_model is not None:
            # Real rows with their missing values against the released table; the model never saw these as such.
            scores["missingness"] = missingness_fidelity(preprocessed.df_processed, final)
        return scores

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
    outdir = Path(base_outdir) / slug(dataset_spec.name or dataset_spec.id)
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

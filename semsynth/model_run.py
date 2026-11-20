"""Fit one model and evaluate what it draws: tables in, metrics out, no files.

:class:`ModelRunner` takes the preprocessed table and one model specification, fits the generator on the training rows, applies
the learned missingness and the skip rules, and computes the requested scores: fidelity to held-out real rows, privacy, joint
fidelity, utility, subgroups, the reference tables and the cross-validation. It returns a :class:`~semsynth.result.SynthesisResult`
with the scores in ``metrics``. :mod:`semsynth.runner` writes the files.
"""

from __future__ import annotations

import logging
from dataclasses import replace
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
from .models import ModelConfigBundle, ModelSpec
from .preprocess import PreprocessingResult
from .result import SynthesisResult
from .synthesis import synthesize
from .utility import tstr_utility, utility_tables

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

LOGGER = logging.getLogger(__name__)

__all__ = ["ModelRunner"]


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


class ModelRunner:
    """Fit one model and evaluate what it generates; nothing here writes a file."""

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

    def run(
        self,
        spec: ModelSpec,
        bundle: ModelConfigBundle,
        preprocessed: PreprocessingResult,
        target: str | None,
        label: str,
    ) -> SynthesisResult:
        """The synthetic table of one model, as released, with its parameters, artifacts and scores.

        Args:
            spec: The model: backend, options, seed, rows and the flags of its own metrics.
            bundle: The bundle that holds the model; its flags are overridden by the pipeline configuration.
            preprocessed: Preprocessed dataset artefacts.
            target: Name of the target column, if the dataset has one.
            label: Name of the run, for the log.
        """

        result, train, holdout, folds = self._generate(spec, preprocessed, target)
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
                pristine, train, holdout, preprocessed, target, int(spec.seed or self._cfg.random_state), label
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
                target,
                spec,
                label,
            )
            if len(folds) > 1:
                metrics["cv"] = self._cross_validate(
                    folds, pristine, preprocessed, target, spec, label
                )
        if downstream_flag and preprocessed.target:
            downstream = _attempt(
                "downstream", label, self._downstream, final, preprocessed, target
            )
            if downstream is not None:
                metrics["downstream"] = downstream
        result = replace(
            result, synthetic_data=final, metrics=metrics, parameters=parameters, artifacts=artifacts
        )
        return replace(
            result, synthetic_data=final, metrics=metrics, parameters=parameters, artifacts=artifacts
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

        codebook = preprocessed.codebook
        if codebook is None:  # nothing declares a rule
            return final
        violations = structural_violations(final, codebook)
        metrics["structure"] = {"violation_rate_before_rules": violations["rate"], "columns": violations["columns"]}
        parameters["structure_aware"] = True
        return enforce_applicability(final, codebook)

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
                role_overrides=self._privacy_roles(),
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
        frame = privacy_frame(
            train, preprocessed.inferred_types, preprocessed.codebook, role_overrides=self._privacy_roles(), target=target
        )
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
            train, preprocessed.inferred_types, preprocessed.codebook, role_overrides=self._privacy_roles(), target=target
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
            target,
            preprocessed.codebook,
            compare=self._downstream_compare,
        )

    def _privacy_roles(self) -> dict[str, str]:
        """The roles that the run declares (``sensitive_columns``); the other columns follow from the codebook and the target."""
        return dict.fromkeys(self._cfg.sensitive_columns, "sensitive")

"""Preparation of a dataset before synthesis: types, codebook, complete rows, sample, missingness model.

Nothing here writes files; the UMAP plot of the real data is drawn by the runner.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .codebook import Codebook
from .config import PipelineConfig
from .specs import DatasetSpec

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

    from .missingness import DataFrameMissingnessModel

LOGGER = logging.getLogger(__name__)

__all__ = ["DatasetPreprocessor", "PreprocessingResult", "UmapArtifacts"]


@dataclass
class UmapArtifacts:
    """What UMAP produced for the real data: the fitted projection, and later its plot."""

    transformer: Any
    real_png: Path | None
    limits: Any | None


@dataclass
class PreprocessingResult:
    """Result values produced by :class:`DatasetPreprocessor`."""

    df_processed: pd.DataFrame
    df_no_na: pd.DataFrame
    df_fit_sample: pd.DataFrame
    disc_cols: list[str]
    cont_cols: list[str]
    inferred_types: dict[str, str]
    codebook_jsonld: dict[str, Any] | None = None
    codebook: Codebook | None = None
    color_series: pd.Series | None = None
    umap_png_real: Path | None = None
    umap_artifacts: UmapArtifacts | None = None
    missingness_model: DataFrameMissingnessModel | None = None


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

    def preprocess(
        self,
        dataset_spec: DatasetSpec,
        df: pd.DataFrame,
        color_series: pd.Series | None,
        cfg: PipelineConfig,
        rng: Any,
        *,
        generate_umap: bool,
        umap_utils: Any | None,
    ) -> PreprocessingResult:
        """Clean data, apply metadata and optionally fit the UMAP projection of the real data.

        Args:
            dataset_spec: Dataset description metadata.
            df: Input dataframe to process.
            color_series: Optional colour labels for UMAP plots.
            cfg: Active pipeline configuration.
            rng: Random state helper returned by ``utils.seed_all``.
            generate_umap: Whether to fit a UMAP projection.
            umap_utils: Module implementing UMAP helper routines.

        Returns:
            Structured container with the processed dataset artefacts used by later stages.
        """

        LOGGER.info(str(cfg))
        codebook = Codebook.from_frame(df, self._declared_codebook(dataset_spec))
        disc_cols, cont_cols = self._split(df, codebook)
        df_processed = self._coerce(df, disc_cols, cont_cols)
        inferred = {
            column: ("discrete" if column in disc_cols else "continuous") for column in df_processed.columns
        }
        df_no_na = df_processed.dropna(axis=0, how="any").reset_index(drop=True)
        if df_no_na.empty:
            df_no_na = df_processed.ffill().bfill().reset_index(drop=True)

        target_series, target_column = self._target_series(dataset_spec, color_series, df_no_na)
        umap_artifacts = (
            self._fit_umap(dataset_spec, df_no_na, disc_cols, cont_cols, target_series, cfg, rng, umap_utils)
            if generate_umap and umap_utils is not None
            else None
        )
        missingness_model = self._fit_missingness(dataset_spec, df_processed, cfg)
        self._complete_codebook(codebook, dataset_spec, df_processed, target_column, missingness_model)

        return PreprocessingResult(
            df_processed=df_processed,
            df_no_na=df_no_na,
            df_fit_sample=self._fit_sample(df_no_na, cfg),
            disc_cols=disc_cols,
            cont_cols=cont_cols,
            inferred_types=inferred,
            codebook_jsonld=codebook.to_jsonld(),
            codebook=codebook,
            color_series=target_series,
            umap_png_real=None,
            umap_artifacts=umap_artifacts,
            missingness_model=missingness_model,
        )

    def _declared_codebook(self, dataset_spec: DatasetSpec) -> Codebook:
        """The codebook that the dataset came with, completed by a curated mapping when there is one."""

        declared = Codebook()
        if dataset_spec.meta is not None:
            try:
                declared = Codebook.read(dataset_spec.meta)
            except Exception:
                LOGGER.exception("Failed to read dataset_spec metadata", extra={"dataset": dataset_spec.name})
        mapping_path = self._resolve_mapping(dataset_spec)
        if mapping_path is None:
            return declared
        LOGGER.info(
            "Applying curated codebook",
            extra={"dataset": dataset_spec.name, "mapping_path": str(mapping_path)},
        )
        try:
            return declared.merged(Codebook.read(self._load_mapping(mapping_path)))
        except Exception:
            LOGGER.exception("Failed to apply curated codebook", extra={"dataset": dataset_spec.name})
            return declared

    def _split(self, df: pd.DataFrame, codebook: Codebook) -> tuple[list[str], list[str]]:
        from .utils import split_columns

        return split_columns(df, codebook, infer=self._utils.infer_types)

    def _coerce(self, df: pd.DataFrame, disc_cols: list[str], cont_cols: list[str]) -> pd.DataFrame:
        processed = self._utils.coerce_discrete_to_category(df, disc_cols)
        processed = self._utils.rename_categorical_categories_to_str(processed, disc_cols)
        return self._utils.coerce_continuous_to_float(processed, cont_cols)

    @staticmethod
    def _target_series(
        dataset_spec: DatasetSpec, color_series: pd.Series | None, df_no_na: pd.DataFrame
    ) -> tuple[pd.Series | None, str | None]:
        """The target column as a series annotated with ``prov:hadRole``, and the name of the target."""

        import pandas as pd

        target_column = dataset_spec.target
        series = None
        if isinstance(color_series, pd.Series) and color_series.name in df_no_na.columns:
            series = df_no_na[color_series.name].copy()
            series.attrs.update(color_series.attrs)
            if target_column and series.attrs.get("prov:hadRole") != "target":
                series.attrs["prov:hadRole"] = "target"
                target_column = series.name
        if series is None and target_column and target_column in df_no_na.columns:
            series = df_no_na[target_column].copy()
            series.attrs["prov:hadRole"] = "target"
        return series, target_column

    @staticmethod
    def _fit_umap(
        dataset_spec: DatasetSpec,
        df_no_na: pd.DataFrame,
        disc_cols: list[str],
        cont_cols: list[str],
        color_series: pd.Series | None,
        cfg: PipelineConfig,
        rng: Any,
        umap_utils: Any,
    ) -> UmapArtifacts | None:
        """Fit the UMAP projection of the real data; ``None`` when the ``umap`` extra is missing or it fails."""

        LOGGER.info("Fitting UMAP on real data sample", extra={"dataset": dataset_spec.name})
        try:
            fitted = umap_utils.build_umap(
                df_no_na,
                disc_cols,
                cont_cols,
                color_series=color_series,
                rng=rng,
                random_state=cfg.random_state,
                max_sample=cfg.max_umap_sample,
                n_neighbors=cfg.umap.n_neighbors,
                min_dist=cfg.umap.min_dist,
                n_components=cfg.umap.n_components,
            )
        except ImportError as exc:
            LOGGER.warning("Skipping UMAP generation: %s", exc, extra={"dataset": dataset_spec.name})
        except Exception:
            LOGGER.exception("UMAP generation failed", extra={"dataset": dataset_spec.name})
        else:
            return UmapArtifacts(transformer=fitted, real_png=None, limits=None)
        return None

    @staticmethod
    def _fit_sample(df_no_na: pd.DataFrame, cfg: PipelineConfig) -> pd.DataFrame:
        if cfg.fit_on_sample and cfg.fit_on_sample < len(df_no_na):
            return df_no_na.sample(cfg.fit_on_sample, random_state=cfg.random_state)
        return df_no_na

    @staticmethod
    def _fit_missingness(
        dataset_spec: DatasetSpec, df_processed: pd.DataFrame, cfg: PipelineConfig
    ) -> DataFrameMissingnessModel | None:
        if not cfg.enable_missingness_wrapping:
            return None
        state = cfg.missingness_random_state
        if state is None:
            state = cfg.random_state
        try:
            from .missingness import fit_missingness_model
        except ImportError:
            LOGGER.warning(
                "Missingness wrapping requested but dependencies are unavailable",
                extra={"dataset": dataset_spec.name},
            )
            return None
        return fit_missingness_model(df_processed, random_state=state)

    @staticmethod
    def _complete_codebook(
        codebook: Codebook,
        dataset_spec: DatasetSpec,
        df_processed: pd.DataFrame,
        target_column: str | None,
        missingness_model: DataFrameMissingnessModel | None,
    ) -> None:
        """Record the target role, the statistics, an identifier and a title in the codebook."""

        if target_column and target_column in df_processed.columns:
            codebook.roles[str(target_column)] = "target"
        codebook.set_statistics(df_processed, missingness_model)
        if "identifier" not in codebook.profile:
            label = dataset_spec.name or str(dataset_spec.id)
            slug = re.sub(r"[^a-z0-9]+", "-", str(label).lower()).strip("-") or "dataset"
            codebook.profile["identifier"] = f"urn:dataset:{slug}"
        if dataset_spec.name and "title" not in codebook.profile:
            codebook.profile["title"] = dataset_spec.name

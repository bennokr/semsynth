"""Missingness modeling utilities for backend generators."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from .metrics import per_variable_distances, summarize_distance_metrics

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder


def _make_one_hot_encoder() -> OneHotEncoder:
    """Instantiate a dense ``OneHotEncoder`` compatible with sklearn versions."""

    from sklearn.preprocessing import OneHotEncoder

    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:  # pragma: no cover - fallback for older sklearn
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def _plain_frame(df: pd.DataFrame) -> pd.DataFrame:
    """A copy of ``df`` without nullable extension dtypes, whose ``pd.NA`` scikit-learn cannot compare."""

    out = df.copy()
    for col in out.columns:
        dtype = out[col].dtype
        if not pd.api.types.is_extension_array_dtype(dtype) or isinstance(dtype, pd.CategoricalDtype):
            continue
        if pd.api.types.is_bool_dtype(dtype):
            out[col] = out[col].astype(object).where(out[col].notna(), np.nan)
        elif pd.api.types.is_numeric_dtype(dtype):
            out[col] = out[col].astype(float)
        else:
            out[col] = out[col].astype(object).where(out[col].notna(), np.nan)
    return out


@dataclass
class ColumnMissingnessModel:
    """Estimate conditional missingness for a single column."""

    col: str
    p_missing_: float = 0.0
    pipeline_: Pipeline | None = None

    def fit(self, df: pd.DataFrame) -> ColumnMissingnessModel:
        """Fit the column-level missingness model.

        Args:
            df: Real dataframe that may contain missing values.

        Returns:
            Self after fitting conditional probability estimators.
        """

        y = df[self.col].isna().astype(int)
        self.p_missing_ = float(y.mean())
        if self.p_missing_ == 0.0 or self.p_missing_ == 1.0:
            self.pipeline_ = None
            return self

        from sklearn.compose import ColumnTransformer, make_column_selector
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline

        X = _plain_frame(df.drop(columns=[self.col]))
        num_selector = make_column_selector(dtype_exclude=["object", "category", "bool"])
        cat_selector = make_column_selector(dtype_include=["object", "category", "bool"])

        numeric_pipe = Pipeline([("imputer", SimpleImputer(strategy="median"))])
        categorical_pipe = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", _make_one_hot_encoder()),
            ]
        )

        pre = ColumnTransformer(
            transformers=[
                ("num", numeric_pipe, num_selector),
                ("cat", categorical_pipe, cat_selector),
            ],
            remainder="drop",
        )

        clf = LogisticRegression(max_iter=200, solver="lbfgs")

        self.pipeline_ = Pipeline([("pre", pre), ("clf", clf)])
        self.pipeline_.fit(X, y)
        return self

    def sample_mask(self, df: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
        """Sample a boolean mask indicating where the column should be missing.

        Args:
            df: Synthetic dataframe prior to applying missingness.
            rng: Random number generator used for reproducibility.

        Returns:
            Boolean series indexed like ``df`` with ``True`` for missing values.
        """

        if self.pipeline_ is None or self.p_missing_ == 0.0:
            if self.p_missing_ == 0.0:
                return pd.Series(False, index=df.index)
            probs = np.full(len(df), self.p_missing_, dtype=float)
        else:
            X = _plain_frame(df.drop(columns=[self.col], errors="ignore"))
            probs = self.pipeline_.predict_proba(X)[:, 1]
            mean_pred = probs.mean()
            if mean_pred > 0:
                scale = self.p_missing_ / mean_pred
                probs = np.clip(probs * scale, 0.0, 1.0)
            else:
                probs[:] = self.p_missing_

        u = rng.random(len(df))
        mask = u < probs
        return pd.Series(mask, index=df.index)


@dataclass
class DataFrameMissingnessModel:
    """Learn and apply missingness patterns across dataframe columns."""

    random_state: int | None = None
    models_: dict[str, ColumnMissingnessModel] = field(default_factory=dict)

    def fit(self, df: pd.DataFrame) -> DataFrameMissingnessModel:
        """Fit per-column missingness models on the provided dataframe.

        Args:
            df: Real dataframe used to learn missingness structure.

        Returns:
            Self with fitted column models.
        """

        self.models_ = {}
        for col in df.columns:
            model = ColumnMissingnessModel(col=col)
            model.fit(df)
            self.models_[col] = model
        return self

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply learned missingness patterns to a synthetic dataframe.

        Args:
            df: Synthetic dataframe before introducing missing values.

        Returns:
            Copy of ``df`` with missingness injected per fitted distributions.
        """

        rng = np.random.default_rng(self.random_state)
        out = df.copy()
        for col, model in self.models_.items():
            if col not in out.columns:
                continue
            mask = model.sample_mask(out, rng)
            out.loc[mask, col] = np.nan
        return out


class MissingnessWrappedGenerator:
    """Wrap a base generator to inject realistic missing values."""

    def __init__(
        self,
        base_generator: Callable[..., pd.DataFrame],
        missingness_model: DataFrameMissingnessModel,
    ) -> None:
        """Initialize the wrapper.

        Args:
            base_generator: Callable that returns a dataframe when invoked with ``n``.
            missingness_model: Learned missingness model to apply to generated data.
        """

        self.base_generator = base_generator
        self.missingness_model = missingness_model

    @classmethod
    def from_real_data(
        cls,
        base_generator: Callable[..., pd.DataFrame],
        real_df: pd.DataFrame,
        random_state: int | None = None,
    ) -> MissingnessWrappedGenerator:
        """Create a wrapper by fitting missingness to real data.

        Args:
            base_generator: Callable producing synthetic samples.
            real_df: Real dataframe used to estimate missingness.
            random_state: Optional RNG seed for reproducibility.

        Returns:
            Configured ``MissingnessWrappedGenerator`` instance.
        """

        miss_model = DataFrameMissingnessModel(random_state=random_state).fit(real_df)
        return cls(base_generator=base_generator, missingness_model=miss_model)

    def sample(self, n: int, **kwargs: Any) -> pd.DataFrame:
        """Generate ``n`` samples with realistic missing values applied."""

        df_syn = self.base_generator(n, **kwargs)
        return self.missingness_model.apply(df_syn)


def fit_missingness_model(
    df: pd.DataFrame, *, random_state: int | None = None
) -> DataFrameMissingnessModel | None:
    """Fit a dataframe-level missingness model with logging safeguards.

    Args:
        df: Dataframe used to estimate missingness behaviour.
        random_state: Optional seed for reproducibility.

    Returns:
        Fitted :class:`DataFrameMissingnessModel` or ``None`` if fitting failed.
    """

    try:
        model = DataFrameMissingnessModel(random_state=random_state)
        return model.fit(df)
    except Exception:  # pragma: no cover - surfaced via pipeline logging
        logging.exception("Failed to fit missingness model", exc_info=True)
        return None


def apply_missingness(
    missingness_model: DataFrameMissingnessModel,
    synth_df: pd.DataFrame,
    real_df: pd.DataFrame,
    disc_cols: Iterable[str],
    cont_cols: Iterable[str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Put learned missingness into a synthetic table and measure it again.

    Args:
        missingness_model: Learned missingness model to apply.
        synth_df: Synthetic table without missing values.
        real_df: Real table without missing values, for the refreshed distances.
        disc_cols: Discrete column names.
        cont_cols: Continuous column names.

    Returns:
        The wrapped table, and the metrics that replace those of the complete table: ``summary``,
        ``per_variable`` and ``missingness_wrapped``.
    """

    wrapped = missingness_model.apply(synth_df).convert_dtypes()
    distances = per_variable_distances(real_df, wrapped, list(disc_cols), list(cont_cols))
    metrics: dict[str, Any] = {
        "summary": summarize_distance_metrics(distances),
        "per_variable": distances.to_dict("records"),
        "missingness_wrapped": True,
    }
    return wrapped, metrics


def missingness_manifest(missingness_model: DataFrameMissingnessModel) -> dict[str, Any]:
    """What the manifest of a run records about the missingness wrapping."""

    return {"wrapped": True, "random_state": missingness_model.random_state, "source": "pipeline"}


def summarize_missingness_model(
    missingness_model: DataFrameMissingnessModel | None,
) -> dict[str, Any] | None:
    """Build a reporting-friendly summary of the missingness model.

    Args:
        missingness_model: Optional fitted missingness model from preprocessing.

    Returns:
        Mapping describing fitted column-level missingness rates or ``None`` if
        no model was provided.
    """

    if missingness_model is None:
        return None

    models = getattr(missingness_model, "models_", {}) or {}
    rows: list[dict[str, float]] = []
    for column, column_model in sorted(models.items()):
        rate = float(getattr(column_model, "p_missing_", 0.0) or 0.0)
        if rate > 0.0:
            rows.append({"column": column, "missing_rate": rate})

    total_columns = len(models)
    nonzero_count = len(rows)
    zero_count = max(total_columns - nonzero_count, 0)

    return {
        "random_state": getattr(missingness_model, "random_state", None),
        "total_columns": total_columns,
        "nonzero_count": nonzero_count,
        "zero_count": zero_count,
        "rows": rows,
    }

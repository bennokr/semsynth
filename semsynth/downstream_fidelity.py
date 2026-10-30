"""Downstream fidelity comparison between real and synthetic data."""

from __future__ import annotations

import json
import logging
import keyword
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd
from pandas.api.types import CategoricalDtype
import statsmodels.api as sm
from makeprov import Config, InPath, OutPath, rule
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression

from .codebook import Codebook, modeling_role

LOGGER = logging.getLogger(__name__)


@dataclass
class DownstreamConfig(Config):
    m: int = 20
    burnin: int = 5
    max_interactions: int = 5
    cv: int = 5


# --- metadata helpers ---------------------------------------------------------
# Metadata is a :class:`Codebook`. A column is looked up as ``(codebook, name)``.
Col = tuple


def _infer_meta(df: pd.DataFrame, target: Optional[str]) -> Codebook:
    roles = {str(col): "target" if target and col == target else "predictor" for col in df.columns}
    return Codebook({"columns": [{"name": str(col)} for col in df.columns]}, roles)  # type: ignore[arg-type]


def _column_lookup(meta: Any) -> Dict[str, Col]:
    meta = meta if isinstance(meta, Codebook) else Codebook.read(meta)
    return {column["name"]: (meta, column["name"]) for column in meta.columns}


def _role(col: Col) -> str:
    meta, name = col
    return modeling_role(meta.roles.get(name))


def _is_cat(col: Col, series: Optional[pd.Series] = None) -> bool:
    meta, name = col
    if (meta.column(name) or {}).get("level") in {"nominal", "categorical", "ordinal"}:
        return True
    if series is not None:
        if isinstance(series.dtype, CategoricalDtype) or pd.api.types.is_bool_dtype(series):
            return True
        if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
            try:
                converted = pd.to_numeric(series.dropna(), errors="coerce")
                if converted.isna().mean() > 0.2:
                    return True
            except Exception:
                return True
    return False


def _levels(col: Col) -> List[str]:
    meta, name = col
    return meta.codes(name)


# --- data prep ----------------------------------------------------------------
def _sanitize_for_formula(
    df_real: pd.DataFrame, df_synth: pd.DataFrame, meta: Codebook
) -> tuple[pd.DataFrame, pd.DataFrame, Codebook]:
    used: set[str] = set()
    rename: Dict[str, str] = {}
    for col in df_real.columns:
        base = "".join(ch if ch.isalnum() else "_" for ch in str(col))
        if base and base[0].isdigit():
            base = f"col_{base}"
        if keyword.iskeyword(base) or base in {"class", "lambda", "return"}:
            base = f"col_{base}" if base else "col"
        name = base or "col"
        suffix = 1
        while name in used:
            name = f"{base}_{suffix}"
            suffix += 1
        used.add(name)
        rename[col] = name

    def _renamed(df: pd.DataFrame) -> pd.DataFrame:
        return df.rename(columns=rename)

    return _renamed(df_real), _renamed(df_synth), meta.rename(rename)


def _coerce_frame(df: pd.DataFrame, meta: Codebook) -> pd.DataFrame:
    df = df.copy()
    for name, col_meta in _column_lookup(meta).items():
        if name not in df.columns:
            continue
        series = df[name]
        if _is_cat(col_meta, series):
            levels = _levels(col_meta)
            if levels:
                df[name] = pd.Categorical(series, categories=levels)
            else:
                df[name] = pd.Categorical(series)
        else:
            numeric = pd.to_numeric(series, errors="coerce")
            if numeric.isna().all() and pd.api.types.is_object_dtype(series):
                df[name] = pd.Categorical(series)
            else:
                df[name] = numeric
    return df


def _impute(df: pd.DataFrame, meta: Codebook) -> pd.DataFrame:
    df = df.copy()
    for name, col_meta in _column_lookup(meta).items():
        if name not in df.columns:
            continue
        series = df[name]
        if series.notna().sum() == 0:
            df = df.drop(columns=[name])
            continue
        if _is_cat(col_meta, series):
            df[name] = df[name].astype("object").fillna("__MISSING__")
        else:
            imp = SimpleImputer(strategy="median")
            df[name] = imp.fit_transform(df[[name]]).ravel()
    return df


# --- formula discovery --------------------------------------------------------
def _var_term(name: str, col_meta: Codebook, series: Optional[pd.Series] = None) -> str:
    quoted = f"Q('{name}')"
    return f"C({quoted}, levels={_levels(col_meta)!r})" if _is_cat(col_meta, series) else quoted


def _build_terms(df: pd.DataFrame, meta: Codebook, max_interactions: int) -> tuple[str, str]:
    lookup = _column_lookup(meta)
    preds = []
    for n, col in lookup.items():
        if _role(col) != "predictor" or n not in df.columns:
            continue
        is_cat = _is_cat(col, df[n])
        if is_cat and not _levels(col):
            # drop empty-level categoricals to avoid patsy contrast errors
            continue
        if df[n].nunique(dropna=True) <= 1:
            continue
        preds.append(n)
    mains = [_var_term(n, lookup[n], df[n]) for n in preds]
    inters: List[str] = []
    for a, b in zip(preds, preds[1:max_interactions + 1]):
        inters.append(f"{_var_term(a, lookup[a], df[a])}:{_var_term(b, lookup[b], df[b])}")
    return mains, inters


def _target_info(meta: Codebook, df: pd.DataFrame) -> tuple[str, str]:
    for name, col_meta in _column_lookup(meta).items():
        if _role(col_meta) == "target":
            if _is_cat(col_meta, df[name]):
                levels = _levels(col_meta) or list(pd.Series(df[name]).dropna().unique())
                return name, "binary" if len(levels) <= 2 else "multiclass"
            return name, "continuous"
    raise ValueError("metadata must define a target column")


def auto_formula(df: pd.DataFrame, meta: Codebook, cfg: DownstreamConfig) -> str:
    df0 = _coerce_frame(df, meta)
    df0 = _impute(df0, meta)
    mains, inters = _build_terms(df0, meta, cfg.max_interactions)
    yname, _ = _target_info(meta, df0)
    if not mains and not inters:
        return f"{yname} ~ 1"
    rhs = " + ".join(mains + inters) or "1"
    return f"{yname} ~ {rhs}"


# --- fitting ------------------------------------------------------------------
def _fit_model(df: pd.DataFrame, formula: str, target_type: str, cfg: DownstreamConfig):
    df_f = df.dropna(axis=0, how="any").copy()
    yname = formula.split("~", 1)[0].strip()
    if yname in df_f.columns:
        if target_type == "multiclass":
            codes = pd.Categorical(df_f[yname]).codes
            df_f = df_f.drop(columns=[yname])
            df_f[yname] = pd.Series(codes, index=df_f.index, dtype="int64")
        elif target_type == "binary":
            codes = pd.Categorical(df_f[yname]).codes.astype(float)
            df_f = df_f.drop(columns=[yname])
            df_f[yname] = pd.Series(codes, index=df_f.index, dtype="float64")
    # Drop zero-variance predictors to avoid Patsy design failures
    for col in list(df_f.columns):
        if col == yname:
            continue
        if df_f[col].nunique(dropna=True) <= 1:
            df_f = df_f.drop(columns=[col])
    if target_type == "multiclass":
        model = sm.MNLogit.from_formula(formula, df_f)
        return model.fit(maxiter=200, disp=False)
    if target_type == "binary":
        model = sm.GLM.from_formula(formula, df_f, family=sm.families.Binomial())
        return model.fit(maxiter=200)
    if target_type == "count":
        model = sm.GLM.from_formula(formula, df_f, family=sm.families.Poisson())
        return model.fit(maxiter=200)
    return sm.OLS.from_formula(formula, df_f).fit()


def _coerce_series(arr_like: Any, *, index: Optional[pd.Index] = None) -> pd.Series:
    if isinstance(arr_like, pd.DataFrame):
        return arr_like.stack()
    if isinstance(arr_like, pd.Series):
        return arr_like
    try:
        return pd.Series(arr_like, index=index)
    except Exception:
        return pd.Series(dtype=float)


# --- public API ---------------------------------------------------------------
def compute_downstream(
    df_real: pd.DataFrame,
    df_synth: pd.DataFrame,
    meta: Any = None,
    *,
    cfg: Optional[DownstreamConfig] = None,
    target: Optional[str] = None,
) -> Mapping[str, Any]:
    cfg = cfg or DownstreamConfig()
    meta_obj = Codebook.read(meta) if meta is not None else _infer_meta(df_real, target)
    df_real, df_synth, meta_obj = _sanitize_for_formula(df_real, df_synth, meta_obj)
    df_real = _coerce_frame(df_real, meta_obj)
    df_synth = _coerce_frame(df_synth, meta_obj)

    try:
        formula = auto_formula(df_real, meta_obj, cfg)
    except Exception as exc:
        LOGGER.error("Auto-formula failed", exc_info=exc)
        return {"formula": None, "compare": None, "skipped_reason": f"formula_error:{exc.__class__.__name__}"}
    if formula.endswith("~ 1"):
        return {"formula": formula, "compare": None, "skipped_reason": "no_predictors"}

    try:
        yname, target_type = _target_info(meta_obj, df_real)
        cols_in_formula = {yname}
        rhs_terms = [t.strip() for t in formula.split("~", 1)[1].split("+")]
        for term in rhs_terms:
            pieces = [p.strip() for p in term.split(":")]
            for piece in pieces:
                piece_clean = (
                    piece.replace("C(", "")
                    .replace("Q('", "")
                    .replace("')", "")
                    .replace(")", "")
                    .replace(" ", "")
                )
                if piece_clean:
                    cols_in_formula.add(piece_clean)
        available = [c for c in df_real.columns if c in df_synth.columns]
        keep = [c for c in available if c in cols_in_formula]
        if yname not in keep:
            keep.append(yname)
        df_real_filtered = df_real[keep].dropna(axis=1, how="all")
        df_synth_filtered = df_synth[keep].dropna(axis=1, how="all")
        # Rebuild formula with only kept terms
        rhs_kept = []
        for term in rhs_terms:
            pieces = [p.strip() for p in term.split(":")]
            if all(
                piece.replace("C(", "")
                .replace("Q('", "")
                .replace("')", "")
                .replace(")", "")
                .replace(" ", "") in keep
                for piece in pieces
            ):
                rhs_kept.append(term)
        rhs_final = " + ".join(rhs_kept) if rhs_kept else "1"
        formula_final = f"{yname} ~ {rhs_final}"

        res_real = _fit_model(df_real_filtered, formula_final, target_type, cfg)
        res_synth = _fit_model(df_synth_filtered, formula_final, target_type, cfg)
    except Exception as exc:
        LOGGER.error("Fit failed", exc_info=exc, extra={"formula": locals().get("formula")})
        return {"formula": formula, "compare": None, "skipped_reason": f"fit_error:{exc.__class__.__name__}"}

    beta_real = _coerce_series(getattr(res_real, "params", None))
    beta_synth = _coerce_series(getattr(res_synth, "params", None))
    se_real = _coerce_series(getattr(res_real, "bse", None))
    se_synth = _coerce_series(getattr(res_synth, "bse", None))
    all_idx = beta_real.index.union(beta_synth.index)
    out = pd.DataFrame(
        {
            "beta_real": beta_real.reindex(all_idx),
            "se_real": se_real.reindex(all_idx),
            "beta_synth": beta_synth.reindex(all_idx),
            "se_synth": se_synth.reindex(all_idx),
        }
    ).assign(sign_match=lambda d: np.sign(d.beta_real) == np.sign(d.beta_synth))
    return {"formula": formula, "compare": out}


@rule(merge=True)
def recompute_downstream(
    metrics: OutPath = OutPath("{metrics}"),
    *,
    real: Optional[InPath] = None,
    synth: Optional[InPath] = None,
    meta: Optional[InPath] = None,
    target: Optional[str] = None,
    verbose: bool = False,
) -> None:
    """Recompute downstream metrics from existing real/synthetic CSVs."""

    if verbose:
        LOGGER.setLevel(logging.INFO)

    metrics_path = Path(metrics)
    model_dir = metrics_path.parent
    dataset_dir = model_dir.parent.parent

    if synth is None:
        synth = model_dir / "synthetic.csv"
    if meta is None:
        meta = dataset_dir / "dataset.codebook.jsonld"
    if real is None:
        manifest_path = model_dir / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            provider = (manifest.get("provider") or "").lower()
            provider_id = manifest.get("provider_id")
            if provider == "uciml" and provider_id is not None:
                candidate = Path("downloads-cache/uciml") / f"{provider_id}.csv.gz"
                if candidate.exists():
                    real = candidate
        except Exception:
            LOGGER.debug("Could not infer provider metadata from %s", manifest_path)

    if real is None or synth is None:
        raise ValueError("real and synth inputs are required or must be discoverable from the model directory")

    real_df = pd.read_csv(real).convert_dtypes()
    synth_df = pd.read_csv(synth).convert_dtypes()

    meta_obj: Optional[Mapping[str, Any]] = None
    if meta is not None:
        meta_obj = json.loads(Path(meta).read_text(encoding="utf-8"))

    results = compute_downstream(real_df, synth_df, meta_obj, target=target)
    compare = results.get("compare")
    sign_match_rate = float("nan")
    if hasattr(compare, "__getitem__"):
        try:
            sign_match_rate = float(compare["sign_match"].astype(float).mean())  # type: ignore[index]
        except Exception:
            sign_match_rate = float("nan")

    payload = {
        "formula": results.get("formula"),
        "sign_match_rate": sign_match_rate,
        "skipped_reason": results.get("skipped_reason"),
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

from .torch_compat import ensure_torch_rmsnorm

LOGGER = logging.getLogger(__name__)

@dataclass
class DatasetPrivacySummary:
    n_real: int
    n_synth: int
    used_columns: List[str]
    qi_columns: List[str]
    sensitive_columns: List[str]
    exact_overlap_rate: float
    near_duplicate_rate_eps: float          # uses synthcity’s close-values threshold (0.2)
    nn_distance_stats: Dict[str, float]     # {'mean','median','p95','min','max'}
    k_min: Optional[int]
    k_pct_lt5: Optional[float]
    k_map: Optional[int]
    rare_qi_reproduction_rate: Optional[float]
    t_closeness: Dict[str, Dict[str, float]]  # per sensitive var: {'mean','p95','max'}
    identifiability_score: Optional[float] = None
    delta_presence: Optional[float] = None


def _tv(p, q) -> float:
    import numpy as np

    idx = p.index.union(q.index)
    return 0.5 * float(np.abs(p.reindex(idx, fill_value=0) - q.reindex(idx, fill_value=0)).sum())

def _w1(x, y) -> float:
    import numpy as np

    x = np.sort(x[~np.isnan(x)]); y = np.sort(y[~np.isnan(y)])
    if len(x) == 0 or len(y) == 0:
        return 0.0
    n = max(len(x), len(y))
    q = (np.arange(n) + 0.5) / n
    return float(np.mean(np.abs(np.quantile(x, q) - np.quantile(y, q))))

def _metric_value(scores, name: str, field: str = "mean") -> Optional[float]:
    """Pull a metric cell from a Metrics.evaluate dataframe."""
    try:
        val = scores.loc[name, field]
    except (KeyError, TypeError):
        return None
    try:
        return float(val)
    except Exception:  # pragma: no cover - float conversion edge cases
        return None


def _normalize_frames(df: "pd.DataFrame",
                      meta: "pd.DataFrame",
                      use_cols: List[str]) -> "pd.DataFrame":
    """Ensure consistent dtypes and missing handling before SynthCity Metrics."""
    import pandas as pd

    tmap = dict(zip(meta.variable, meta.type))
    cat_cols = [c for c in use_cols if tmap.get(c) not in ("numeric", "datetime")]
    num_cols = [c for c in use_cols if tmap.get(c) == "numeric"]
    dt_cols = [c for c in use_cols if tmap.get(c) == "datetime"]

    out = df.copy()
    for c in cat_cols:
        out[c] = out[c].astype("string")
        out[c] = out[c].fillna("<MISSING>")
    for c in num_cols:
        out[c] = pd.to_numeric(out[c], errors="raise")
        if out[c].isna().any():
            out[c] = out[c].fillna(out[c].median())
    for c in dt_cols:
        x = pd.to_datetime(out[c], errors="coerce")
        med = x.view("int64").dropna().median() if x.notna().any() else 0
        out[c] = x.view("int64").fillna(med)
    return out


def summarize_privacy_synthcity(df_real: "pd.DataFrame",
                                df_synth: "pd.DataFrame",
                                meta: "pd.DataFrame",
                                *,
                                eps: float = 0.1) -> DatasetPrivacySummary:
    """Summarize privacy metrics using SynthCity on aligned real/synthetic dataframes.

    Args:
        df_real: Real dataframe.
        df_synth: Synthetic dataframe.
        meta: Metadata with variable roles and types.
        eps: Unused hook for future custom thresholds; kept for API stability.

    Returns:
        DatasetPrivacySummary with overlap, neighbor, k-map, t-closeness, and
        optional identifiability/delta-presence scores.
    """
    import numpy as np
    import pandas as pd

    ensure_torch_rmsnorm()
    try:
        from synthcity.metrics import Metrics
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Privacy metrics require 'synthcity'; install with pip install semsynth[synthcity]"
        ) from exc

    # select columns
    assert {'variable','role','type'}.issubset(meta.columns)
    use_meta = meta[~meta.role.isin(['ignore', 'id', 'target'])].copy()
    use_cols = [c for c in use_meta.variable if c in df_real.columns and c in df_synth.columns]
    if not use_cols: raise ValueError("No overlapping usable columns.")
    qi = [c for c in use_meta.loc[use_meta.role=='qi','variable'] if c in use_cols]
    sens = [c for c in use_meta.loc[use_meta.role=='sensitive','variable'] if c in use_cols]

    # preprocess with explicit dtype normalization
    df_r = _normalize_frames(df_real[use_cols], use_meta, use_cols)
    df_s = _normalize_frames(df_synth[use_cols], use_meta, use_cols)

    # synthcity metrics using shared encoders across real/synth
    metrics_spec = {
        "sanity": ["common_rows_proportion", "close_values_probability", "nearest_syn_neighbor_distance"],
        "privacy": ["k-map", "delta-presence", "identifiability_score"],
    }
    try:
        scores = Metrics.evaluate(X_gt=df_r, X_syn=df_s, metrics=metrics_spec)
    except Exception as exc:  # pragma: no cover - depends on optional deps
        LOGGER.warning("SynthCity Metrics.evaluate failed: %s", exc)
        scores = None

    exact_overlap_val = _metric_value(scores, "sanity.common_rows_proportion.score") if scores is not None else None
    exact_overlap = float(exact_overlap_val) if exact_overlap_val is not None else float("nan")
    close_prob_val = _metric_value(scores, "sanity.close_values_probability.score") if scores is not None else None
    close_prob = float(close_prob_val) if close_prob_val is not None else float("nan")
    nn_mean = _metric_value(scores, "sanity.nearest_syn_neighbor_distance.mean") if scores is not None else None
    nn_median = _metric_value(scores, "sanity.nearest_syn_neighbor_distance.mean", "median") if scores is not None else None
    nn_min = _metric_value(scores, "sanity.nearest_syn_neighbor_distance.mean", "min") if scores is not None else None
    nn_max = _metric_value(scores, "sanity.nearest_syn_neighbor_distance.mean", "max") if scores is not None else None
    nn_stats = {
        'mean': float(nn_mean) if nn_mean is not None else float("nan"),
        'median': float(nn_median) if nn_median is not None else float("nan"),
        'p95': np.nan,
        'min': float(nn_min) if nn_min is not None else float("nan"),
        'max': float(nn_max) if nn_max is not None else float("nan"),
    }

    # k-anon on real QIs and k-map on QIs
    if qi:
        eq_sizes = df_r.groupby(qi, dropna=False).size().to_numpy()
        k_min = int(eq_sizes.min()) if eq_sizes.size else None
        k_pct_lt5 = float((eq_sizes < 5).mean()) if eq_sizes.size else None
        k_map_val = _metric_value(scores, "privacy.k-map.score") if scores is not None else None
        if k_map_val is not None and not np.isnan(k_map_val):
            k_map_val = int(k_map_val)
        else:
            k_map_val = None
    else:
        k_min = k_pct_lt5 = k_map_val = None

    ident = _metric_value(scores, "privacy.identifiability_score.score") if scores is not None else None
    if ident is not None and np.isnan(ident):
        ident = None
    delta = _metric_value(scores, "privacy.delta-presence.score") if scores is not None else None
    if delta is not None and np.isnan(delta):
        delta = None
    if scores is not None and delta is None:
        LOGGER.info("Delta presence not returned by SynthCity; leaving unset.")

    # rare QI reproduction (real count<=5 or freq<=1%)
    if qi:
        cnt = df_r.groupby(qi, dropna=False).size()
        rare = set(cnt[(cnt <= 5) | (cnt/len(df_r) <= 0.01)].index)
        syn_keys = set(df_s.groupby(qi, dropna=False).size().index)
        rare_rate = len(rare & syn_keys) / len(rare) if rare else 0.0
    else:
        rare_rate = None

    # t-closeness per sensitive var (TV for categoricals; W1 for numerics)
    tmap = dict(zip(use_meta.variable, use_meta.type))
    t_close: Dict[str, Dict[str, float]] = {}
    if qi and sens:
        groups = df_s.groupby(qi, dropna=False)
        for s_col in sens:
            if tmap.get(s_col) == 'numeric':
                gref = df_r[s_col].to_numpy(float)
                vals = [ _w1(g[s_col].to_numpy(float), gref) for _, g in groups ]
            else:
                pref = df_r[s_col].astype('object').value_counts(normalize=True, dropna=False)
                vals = [ _tv(g[s_col].astype('object').value_counts(normalize=True, dropna=False), pref)
                         for _, g in groups ]
            if vals:
                arr = np.array(vals, float)
                t_close[s_col] = {'mean': float(arr.mean()),
                                  'p95': float(np.quantile(arr, 0.95)),
                                  'max': float(arr.max())}
    # package
    return DatasetPrivacySummary(
        n_real=len(df_r),
        n_synth=len(df_s),
        used_columns=use_cols,
        qi_columns=qi,
        sensitive_columns=sens,
        exact_overlap_rate=exact_overlap,
        near_duplicate_rate_eps=close_prob,     # synthcity’s fixed threshold
        nn_distance_stats=nn_stats,
        k_min=k_min,
        k_pct_lt5=k_pct_lt5,
        k_map=k_map_val,
        rare_qi_reproduction_rate=rare_rate,
        t_closeness=t_close,
        identifiability_score=ident,
        delta_presence=delta,
    )

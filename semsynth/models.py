"""Model configuration loading and run discovery utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import tomllib

from makeprov import OutPath, rule
from makeprov.config import Config

if False:  # pragma: no cover - imported for type checking only
    from typing import TypedDict  # noqa: F401  # pylint: disable=unused-import


@dataclass
class ModelSpec:
    """Specification for invoking a backend model run."""

    name: str
    backend: str
    model: Dict[str, Any] = field(default_factory=dict)
    rows: Optional[int] = None
    seed: Optional[int] = None
    compute_privacy: Optional[bool] = None
    compute_downstream: Optional[bool] = None


@dataclass
class ModelConfigBundle(Config):
    """Container bundling model specs together with global run flags."""

    specs: List[ModelSpec]
    generate_umap: Optional[bool] = None
    compute_privacy: Optional[bool] = None
    compute_downstream: Optional[bool] = None
    enable_missingness_wrapping: Optional[bool] = None


@dataclass
class ModelRun:
    """Metadata describing an executed model run on disk."""

    name: str
    backend: str
    run_dir: Path
    synthetic_csv: Path
    per_variable_csv: Optional[Path]
    metrics_json: Optional[Path]
    metrics: Dict[str, Any]
    umap_png: Optional[Path]
    manifest: Dict[str, Any]
    privacy_json: Optional[Path]
    privacy_metrics: Dict[str, Any] = field(default_factory=dict)
    downstream_json: Optional[Path] = None
    downstream_metrics: Dict[str, Any] = field(default_factory=dict)


def _as_list(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("models", "configs", "generators"):
            if isinstance(data.get(key), list):
                return list(data[key])
        return []
    if isinstance(data, list):
        return list(data)
    return []


def _coerce_optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        val = value.strip().lower()
        if val in {"true", "yes", "1", "on"}:
            return True
        if val in {"false", "no", "0", "off"}:
            return False
    raise ValueError(f"Cannot coerce value {value!r} to boolean")


def parse_toml_config(config_input: Optional[str]) -> Dict[str, Any]:
    """Parse a TOML configuration from a file (prefixed with ``@``) or inline snippet."""

    if not config_input:
        return {}
    text = ""
    candidate = config_input.strip()
    if candidate.startswith("@"):
        path = Path(candidate[1:]).expanduser()
        text = path.read_text(encoding="utf-8")
    else:
        maybe_path = Path(candidate).expanduser()
        if maybe_path.exists():
            text = maybe_path.read_text(encoding="utf-8")
        else:
            text = candidate
    data = tomllib.loads(text)
    return data or {}


def _extract_globals(data: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Optional[bool]]]:
    items = _as_list(data)
    globals_src: Dict[str, Any] = {}
    if isinstance(data, dict):
        globals_src.update({k: data.get(k) for k in ("generate_umap", "compute_privacy", "compute_downstream", "enable_missingness_wrapping")})
        nested = data.get("globals")
        if isinstance(nested, dict):
            globals_src.update({k: nested.get(k) for k in ("generate_umap", "compute_privacy", "compute_downstream", "enable_missingness_wrapping")})
    globals_map = {
        key: _coerce_optional_bool(value)
        for key, value in globals_src.items()
        if value is not None
    }
    return items, globals_map


@rule(merge=True, phony=True)
def load_model_configs(config_input: Optional[str] = None, *, config_data: Optional[Dict[str, Any]] = None) -> ModelConfigBundle:
    """Load model specifications and global flags from TOML."""

    data: Any = config_data if config_data is not None else parse_toml_config(config_input)
    items, globals_map = _extract_globals(data)
    specs: List[ModelSpec] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Config item at index {idx} must be a mapping")
        name = str(item.get("name") or f"model_{idx + 1}")
        backend = str(item.get("backend") or "pybnesian").strip().lower()
        model = item.get("model") or {}
        rows = item.get("rows")
        seed = item.get("seed")
        compute_privacy = _coerce_optional_bool(item.get("compute_privacy"))
        compute_downstream = _coerce_optional_bool(item.get("compute_downstream"))
        specs.append(
            ModelSpec(
                name=name,
                backend=backend,
                model=dict(model),
                rows=int(rows) if rows is not None else None,
                seed=int(seed) if seed is not None else None,
                compute_privacy=compute_privacy,
                compute_downstream=compute_downstream,
            )
        )
        logging.debug(
            "Loaded model spec: name=%s backend=%s rows=%s seed=%s", name, backend, rows, seed
        )
    logging.info("Loaded %d model configs", len(specs))
    return ModelConfigBundle(
        specs=specs,
        generate_umap=globals_map.get("generate_umap"),
        compute_privacy=globals_map.get("compute_privacy"),
        compute_downstream=globals_map.get("compute_downstream"),
        enable_missingness_wrapping=globals_map.get("enable_missingness_wrapping"),
    )


@rule(merge=True, phony=True)
def model_run_root(dataset_outdir: Path | OutPath) -> Path:
    root = dataset_outdir / "models"
    root.mkdir(parents=True, exist_ok=True)
    return root


@rule(merge=True, phony=True)
def model_run_dir(dataset_outdir: Path | OutPath, name: str) -> Path:
    root = model_run_root(dataset_outdir)
    run_dir = root / str(name)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


@rule(merge=True, phony=True)
def write_manifest(run_dir: Path | OutPath, manifest: Dict[str, Any]) -> None:
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logging.debug("Wrote manifest to %s", run_dir / "manifest.json")


@rule(merge=True, phony=True)
def discover_model_runs(dataset_outdir: str | Path) -> List[ModelRun]:
    root = Path(dataset_outdir) / "models"
    if not root.exists():
        logging.info("No model runs found under %s", root)
        return []

    runs: List[ModelRun] = []
    for run_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        backend = str(manifest.get("backend") or "").lower()
        name = str(manifest.get("name") or run_dir.name)
        synthetic_csv = run_dir / "synthetic.csv"
        per_var = run_dir / "per_variable_metrics.csv"
        metrics_json = run_dir / "metrics.json"
        privacy_json = run_dir / "metrics.privacy.json"
        downstream_json = run_dir / "metrics.downstream.json"
        metrics: Dict[str, Any] = {}
        privacy_metrics: Dict[str, Any] = {}
        downstream_metrics: Dict[str, Any] = {}
        for path, target in (
            (metrics_json, metrics),
            (privacy_json, privacy_metrics),
            (downstream_json, downstream_metrics),
        ):
            if path.exists():
                try:
                    target.update(json.loads(path.read_text(encoding="utf-8")))
                except Exception:
                    target.clear()

        umap_png = run_dir / "umap.png"
        if not umap_png.exists():
            umap_png = None

        runs.append(
            ModelRun(
                name=name,
                backend=backend,
                run_dir=run_dir,
                synthetic_csv=synthetic_csv,
                per_variable_csv=per_var if per_var.exists() else None,
                metrics_json=metrics_json if metrics_json.exists() else None,
                metrics=metrics,
                umap_png=umap_png,
                manifest=manifest,
                privacy_json=privacy_json if privacy_json.exists() else None,
                privacy_metrics=privacy_metrics,
                downstream_json=downstream_json if downstream_json.exists() else None,
                downstream_metrics=downstream_metrics,
            )
        )

    logging.info("Discovered %d model runs under %s", len(runs), root)
    return runs

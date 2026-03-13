from __future__ import annotations
import json
from importlib import resources as _importlib_resources
from typing import Any, Dict, List, Mapping, Optional
from enum import Enum
from dataclasses import dataclass

from makeprov import RDFMixin

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pint_pandas import PintType

from .utils import normalize_variable_descriptors, normalize_role, get_column_name


def _load_context() -> dict:
    data = _importlib_resources.files("semsynth").joinpath("context.jsonld").read_text("utf-8")
    return json.loads(data)


CONTEXT = _load_context()

# --- SKOS mapping mixin -------------------------------------------------------
@dataclass(kw_only=True)
class SkosMappings(RDFMixin):
    exactMatch: Optional[List[str]] = None
    closeMatch: Optional[List[str]] = None
    broadMatch: Optional[List[str]] = None
    narrowMatch: Optional[List[str]] = None
    relatedMatch: Optional[List[str]] = None


# --- Code book (SKOS) ---------------------------------------------------------
@dataclass
class CodeConcept(SkosMappings):
    notation: Optional[str] = None
    prefLabel: Optional[str] = None


@dataclass
class CodeBook(RDFMixin):
    hasTopConcept: Optional[List[CodeConcept]] = None
    source: Optional[str] = None  # if different from ColumnProperty source


# --- Column property (DSV + QUDT/UCUM) ---------------------------------------
class StatisticalDataType(str, Enum):
    Interval = "dsv:IntervalDataType"
    Nominal = "dsv:NominalDataType"
    Numerical = "dsv:NumericalDataType"
    Ordinal = "dsv:OrdinalDataType"
    Ratio = "dsv:RatioDataType"


@dataclass
class SummaryStatistics(RDFMixin):
    statisticalDataType: Optional[StatisticalDataType] = None
    columnCompleteness: Optional[float] = None
    datasetCompleteness: Optional[float] = None
    numberOfRows: Optional[int] = None
    numberOfColumns: Optional[int] = None
    missingValueFormat: Optional[str] = None
    meanValue: Optional[float] = None
    medianValue: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None


class Unit(SkosMappings):
    ucumCode: Optional[str] = None  # e.g., "a"


@dataclass
class ColumnProperty(SkosMappings, RDFMixin):
    summaryStatistics: Optional[SummaryStatistics] = None
    unitText: Optional[str] = None  # e.g., "unit:YR" or "year"
    hasUnit: Optional[Unit] = None  # Unit node with possible QUDT IRI skos match
    source: Optional[str] = None  # web page with documentation
    hasCodeBook: Optional[CodeBook] = None
    hasVariable: str | CodeConcept | None = None  # link to variable definition


# --- CSVW/DSV column and schema ----------------------------------------------
@dataclass
class Column(RDFMixin):
    name: str  # required
    titles: str | list[str] | None = None
    description: Optional[str] = None
    identifier: Optional[str] = None
    about: Optional[str] = None
    hadRole: Optional[str] = None
    defaultValue: Optional[Any] = None
    columnProperty: Optional[ColumnProperty] = None
    summaryStatistics: Optional[SummaryStatistics] = None


@dataclass
class DatasetSchema(RDFMixin):
    __context__ = CONTEXT
    columns: List[Column]  # required


# --- Root document / Dataset --------------------------------------------------
@dataclass
class Metadata(RDFMixin):
    __context__ = CONTEXT
    datasetSchema: DatasetSchema  # required
    summaryStatistics: Optional[SummaryStatistics] = None
    title: Optional[str] = None
    description: Optional[str] = None
    abstract: Optional[str] = None
    purpose: Optional[str] = None
    landingPage: Optional[str] = None
    tableOfContents: Optional[str] = None
    citation: Optional[Any] = None
    provider: Optional[str] = None
    identifier: Optional[Any] = None
    funding: Optional[Any] = None
    populationType: Optional[Any] = None
    accessRights: Optional[Any] = None

    @classmethod
    def from_dcat_dsv(cls, payload: Mapping[str, Any]) -> "Metadata":
        """Build a :class:`Metadata` instance from a DCAT/DSV JSON-LD payload.

        Args:
            payload: Raw JSON-LD mapping created by :mod:`semsynth.dataproviders.uciml`.

        Returns:
            Parsed metadata with dataset- and column-level attributes populated.
        """

        def _get(*keys: str) -> Optional[Any]:
            for key in keys:
                if key in payload:
                    return payload.get(key)
            return None

        ds_summary = payload.get("dsv:summaryStatistics") or {}
        ds_stats = SummaryStatistics(
            datasetCompleteness=ds_summary.get("dsv:datasetCompleteness"),
            numberOfRows=ds_summary.get("dsv:numberOfRows"),
            numberOfColumns=ds_summary.get("dsv:numberOfColumns"),
            missingValueFormat=ds_summary.get("dsv:missingValueFormat"),
        ) if isinstance(ds_summary, Mapping) else None

        schema = payload.get("dsv:datasetSchema") or payload.get("datasetSchema") or {}
        columns_json: List[Mapping[str, Any]] = []
        if isinstance(schema, Mapping):
            raw_columns = schema.get("dsv:column") or schema.get("columns") or []
            if isinstance(raw_columns, Mapping):
                columns_json = [raw_columns]
            elif isinstance(raw_columns, list):
                columns_json = [c for c in raw_columns if isinstance(c, Mapping)]

        descriptor_lookup = {
            descriptor.name: descriptor
            for descriptor in normalize_variable_descriptors(columns_json)
        }

        columns: List[Column] = []
        for col_json in columns_json:
            summary = col_json.get("dsv:summaryStatistics") or col_json.get("summaryStatistics")
            if isinstance(summary, Mapping):
                normalized_summary = {}
                for key, value in summary.items():
                    clean_key = key.split(":", maxsplit=1)[-1] if key.startswith("dsv:") else key
                    normalized_summary[clean_key] = value
                column_stats = SummaryStatistics.from_jsonld(normalized_summary)
            else:
                column_stats = None
            col_prop_json = col_json.get("dsv:columnProperty") or col_json.get("columnProperty")
            col_prop = ColumnProperty.from_jsonld(col_prop_json) if isinstance(col_prop_json, Mapping) else None
            descriptor = descriptor_lookup.get(
                get_column_name(col_json) or ""
            )
            unit_text = (
                descriptor.unit if descriptor and descriptor.unit else None
            ) or col_json.get("schema:unitText") or col_json.get("unitText")
            if unit_text:
                if col_prop is None:
                    col_prop = ColumnProperty(unitText=unit_text)
                elif not col_prop.unitText:
                    col_prop.unitText = unit_text
            name = get_column_name(col_json)
            if not name:
                continue
            descriptor = descriptor_lookup.get(str(name))
            description = descriptor.description if descriptor and descriptor.description else col_json.get("dcterms:description")
            role = descriptor.role if descriptor and descriptor.role else col_json.get("prov:hadRole")
            columns.append(
                Column(
                    name=name,
                    titles=col_json.get("csvw:titles") or col_json.get("titles") or col_json.get("dcterms:title"),
                    description=description,
                    about=col_json.get("schema:about"),
                    hadRole=role,
                    identifier=col_json.get("schema:identifier"),
                    defaultValue=col_json.get("schema:defaultValue"),
                    columnProperty=col_prop,
                    summaryStatistics=column_stats,
                )
            )

        dataset_schema = DatasetSchema(columns=columns)

        return cls(
            datasetSchema=dataset_schema,
            summaryStatistics=ds_stats,
            title=_get("dcterms:title"),
            description=_get("dcterms:description"),
            abstract=_get("dcterms:abstract"),
            purpose=_get("dcterms:purpose"),
            landingPage=_get("dcat:landingPage"),
            tableOfContents=_get("dcterms:tableOfContents"),
            citation=_get("schema:citation"),
            provider=_get("dcterms:creator", "prov:wasAttributedTo"),
            identifier=_get("dcterms:identifier"),
            funding=_get("schema:funding"),
            populationType=_get("schema:populationType"),
            accessRights=_get("dcterms:accessRights"),
        )

    def to_privacy_frame(self, inferred: Mapping[str, str]) -> "pd.DataFrame":
        """Build a privacy metadata dataframe from SemMap content.

        The privacy metrics expect roles such as ``qi`` and ``sensitive`` and a
        coarse type mapping (``numeric``/``categorical``/``datetime``). This
        helper normalizes SemMap roles to those expectations and uses
        ``statisticalDataType`` or codebooks to infer the variable types,
        falling back to the provided ``inferred`` mapping when semantics are
        absent.

        Args:
            inferred: Mapping of column names to inferred types (``discrete`` or
                ``continuous``) used as fallback when semantics are missing.

        Returns:
            Dataframe with ``variable``, ``role`` and ``type`` columns.
        """

        import pandas as pd

        rows = []
        
        def _statistical_dtype(node: Optional[Any]) -> Optional[str]:
            stat_node = node.summaryStatistics if getattr(node, "summaryStatistics", None) else node
            raw_type = getattr(stat_node, "statisticalDataType", None)
            if raw_type:
                return raw_type.value if hasattr(raw_type, "value") else str(raw_type)
            if isinstance(stat_node, ColumnProperty) and stat_node.hasCodeBook:
                return "dsv:NominalDataType"
            return None

        for col in self.datasetSchema.columns:
            role = normalize_role(col.hadRole)
            dtype = None
            stats_nodes = [col.summaryStatistics, getattr(col, "columnProperty", None)]
            for node in stats_nodes:
                dtype = _statistical_dtype(node)
                if dtype:
                    break
            inferred_kind = inferred.get(col.name, "continuous")
            mapped_dtype = "numeric" if inferred_kind == "continuous" else "categorical"
            if dtype:
                lowered = dtype.lower()
                if "nominal" in lowered or "ordinal" in lowered:
                    mapped_dtype = "categorical"
                elif "interval" in lowered or "ratio" in lowered or "numerical" in lowered:
                    mapped_dtype = "numeric"
            rows.append({"variable": col.name, "role": role, "type": mapped_dtype})
        return pd.DataFrame(rows)

    def update_completeness_from_missingness(
        self,
        df: "pd.DataFrame",
        missingness_model: Optional[Any],
    ) -> None:
        """Refresh completeness and missing-value annotations based on fitted models.

        Args:
            df: Dataframe used to compute dataset completeness.
            missingness_model: Optional :class:`DataFrameMissingnessModel` instance
                containing per-column missingness probabilities.
        """

        import pandas as pd

        if not isinstance(df, pd.DataFrame):
            return

        n_rows, n_cols = df.shape
        total_cells = n_rows * n_cols
        nnz = int(df.notna().to_numpy().sum())
        completeness = nnz / float(total_cells) if total_cells else 1.0

        if not self.summaryStatistics:
            self.summaryStatistics = SummaryStatistics()
        self.summaryStatistics.numberOfRows = n_rows
        self.summaryStatistics.numberOfColumns = n_cols
        self.summaryStatistics.datasetCompleteness = completeness

        model_map = getattr(missingness_model, "models_", {}) or {}
        by_name = {col.name: col for col in self.datasetSchema.columns}
        for col_name, col in by_name.items():
            model = model_map.get(col_name)
            if model is None:
                rate = float(df[col_name].isna().mean()) if col_name in df.columns else 0.0
            else:
                rate = float(getattr(model, "p_missing_", 0.0) or 0.0)
            completeness_val = 1.0 - rate
            if not col.summaryStatistics:
                col.summaryStatistics = SummaryStatistics()
            col.summaryStatistics.columnCompleteness = completeness_val

    def to_jsonld(self) -> Optional[Dict[str, Any]]:  # type: ignore[override]
        return super().to_jsonld()


# Arrow metadata keys (bytes per Arrow requirements)
_DATASET_SEMMAP_KEY = b"semmap.dataset"
_COLUMN_SEMMAP_KEY = b"semmap.column"


@pd.api.extensions.register_series_accessor("semmap")
class SemMapSeriesAccessor:
    """Series-level accessor to attach metadata semantics."""

    def __init__(self, s: pd.Series) -> None:
        self._s = s
        stored = s.attrs.get("semmap_col")
        self.col_semmap = stored if isinstance(stored, Column) else None

    def _persist_col_semmap(self) -> None:
        """Persist column semantics in ``Series.attrs`` for accessor re-instantiation."""

        if self.col_semmap is not None:
            self._s.attrs["semmap_col"] = self.col_semmap

    # ---- helpers -------------------------------------------------------------

    def _try_convert_to_pint(self) -> None:
        """Best-effort conversion of the Series to a pint dtype using unit_text."""
        # Derive unit_text from UCUM if needed
        if not self.col_semmap:
            return
        col_prop = self.col_semmap.columnProperty
        if col_prop is None:
            return
        ucum_code = col_prop.hasUnit.ucumCode if col_prop.hasUnit else None
        
        if col_prop.unitText is None and ucum_code is not None:
            try:
                from ucumvert import PintUcumRegistry

                ureg = PintUcumRegistry()
                col_prop.unitText = str(ureg.from_ucum(ucum_code).units)
            except Exception:
                pass

        if col_prop.unitText is None:
            return
        try:
            self._s[:] = self._s.astype(f"pint[{col_prop.unitText}]")
        except Exception:
            # Swallow conversion errors—metadata is still attached
            pass

    # ---- Declarative APIs ----------------------------------------------------

    def set_numeric(
        self,
        name: str,
        label: str,
        *,
        unit_text: Optional[str] = None,  # unit string ("mmHg", "mg/dL", "year")
        ucum_code: Optional[str] = None,  # UCUM code ("mm[Hg]", "mg/dL", "a")
        qudt_unit_iri: Optional[str] = None,  # QUDT IRI
        source_iri: Optional[str] = None,
        convert_to_pint: bool = True,
    ) -> "SemMapSeriesAccessor":
        """Attach numeric variable metadata and (optionally) convert dtype to pint."""
        # Units node/string based on available inputs
        has_unit: str | Unit | None = None
        # If both UCUM and QUDT provided, use a Unit node to capture both
        if ucum_code or qudt_unit_iri:
            if qudt_unit_iri:
                has_unit = Unit(ucumCode=ucum_code, exactMatch=[qudt_unit_iri])
            elif ucum_code:
                has_unit = Unit(ucumCode=ucum_code)

        col_prop = ColumnProperty(
            unitText=unit_text,
            hasUnit=has_unit,
            source=source_iri,
        )

        # Attach semantics to the Series (serialize dataclasses)
        self.col_semmap = Column(name=name, titles=label, columnProperty=col_prop)

        # Optionally convert to pint dtype
        if convert_to_pint:
            self._try_convert_to_pint()
        self._persist_col_semmap()

        return self

    def set_categorical(
        self,
        name: str,
        label: str,
        *,
        codes: dict[int | str, str],
        scheme_source_iri: Optional[str] = None,
        source_iri: Optional[str] = None,
    ) -> "SemMapSeriesAccessor":
        """Attach categorical variable metadata (integer-coded or strings)."""
        # Build SKOS CodeBook with CodeConcepts
        top_concepts = [
            CodeConcept(notation=str(code), prefLabel=pref)
            for code, pref in codes.items()
        ]

        col_prop = ColumnProperty(
            hasCodeBook=CodeBook(hasTopConcept=top_concepts, source=scheme_source_iri),
            source=source_iri,
        )

        # Attach SemMap to the Series
        self.col_semmap = Column(name=name, titles=label, columnProperty=col_prop)

        # Ensure pandas categorical dtype if appropriate (best-effort)
        try:
            if not isinstance(self._s.dtype, pd.CategoricalDtype):
                self._s[:] = self._s.astype("category")
        except Exception:
            pass

        self._persist_col_semmap()
        return self
    
    def _infer_statistical_data_type(self) -> StatisticalDataType:
        """Heuristic statistical data type inference for the Series."""
        if isinstance(self._s.dtype, pd.CategoricalDtype):
            # pandas categorical supports ordered attribute
            if getattr(getattr(self._s, "cat", None), "ordered", False):
                return StatisticalDataType.Ordinal
            else: 
                return StatisticalDataType.Nominal
        if isinstance(self._s.dtype, pd.BooleanDtype):
            return StatisticalDataType.Nominal
        return StatisticalDataType.Numerical

    # ---- Introspection -------------------------------------------------------
    def __call__(self) -> Column:
        if self.col_semmap is None:
            self.col_semmap = Column(name=str(self._s.name or ""))
        n = len(self._s)
        if self.col_semmap is None:
            self.col_semmap = Column(name=str(self._s.name))
        self.col_semmap.summaryStatistics = SummaryStatistics(
            statisticalDataType=self._infer_statistical_data_type(),
            columnCompleteness=float(self._s.notna().mean()) if n else 1.0,
            numberOfRows=n,
        )
        self._persist_col_semmap()
        return self.col_semmap

    def from_jsonld(self, metadata: Dict[str, Any], convert_pint: bool = True) -> "SemMapSeriesAccessor":
        """Attach column semantics from a JSON-LD payload.

        Args:
            metadata: Column-level JSON-LD mapping.
            convert_pint: Whether to attempt pint dtype conversion.

        Returns:
            Accessor instance for chaining.
        """

        self.col_semmap = Column.from_jsonld(metadata)

        if isinstance(metadata, Mapping):
            if not getattr(self.col_semmap, "name", None):
                self.col_semmap.name = (
                    metadata.get("name")
                    or metadata.get("schema:name")
                    or metadata.get("identifier")
                    or metadata.get("schema:identifier")
                    or str(self._s.name)
                )
            col_prop_json = metadata.get("columnProperty") or metadata.get("dsv:columnProperty")
            if isinstance(col_prop_json, Mapping):
                try:
                    self.col_semmap.columnProperty = ColumnProperty.from_jsonld(col_prop_json)
                except Exception:
                    unit_text = col_prop_json.get("unitText") or col_prop_json.get("schema:unitText")
                    has_unit = col_prop_json.get("hasUnit")
                    ucum_code = None
                    if isinstance(has_unit, Mapping):
                        ucum_code = has_unit.get("ucumCode") or has_unit.get("qudt:ucumCode")
                    unit_node = Unit(ucumCode=str(ucum_code)) if ucum_code else None
                    self.col_semmap.columnProperty = ColumnProperty(
                        unitText=str(unit_text) if unit_text else None,
                        hasUnit=unit_node,
                    )

        if convert_pint:
            self._try_convert_to_pint()
        self._persist_col_semmap()
        return self

    def to_jsonld(self) -> Optional[Dict[str, Any]]:
        return self().to_jsonld()

    # ---- internal hook (used by DataFrame writer) ----------------------------

    def _ensure_storage_for_parquet(self) -> pd.Series:
        """Ensure the physical storage is parquet-friendly (e.g., strip pint to magnitudes)."""
        s = self._s
        if isinstance(s.dtype, PintType):
            # Store magnitudes; metadata carries units for reconstruction
            try:
                magnitudes = s.to_numpy().magnitude
            except Exception:
                try:
                    magnitudes = s.array.quantity.magnitude
                except Exception:
                    magnitudes = [getattr(value, "magnitude", value) for value in s.to_numpy()]
            s = pd.Series(magnitudes, index=s.index, name=s.name)
        return s


@pd.api.extensions.register_dataframe_accessor("semmap")
class SemMapFrameAccessor:
    """DataFrame-level accessor for dataset metadata and Parquet round-trip."""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df
        self.dataset_semmap = None

    # ---- Helpers -------------------------------------------------------------
    
    def __call__(self) -> Metadata:
        # columns
        if not self.dataset_semmap:
            self.dataset_semmap = Metadata(datasetSchema=DatasetSchema(columns=[]))
        cols = [self._df[col].semmap() for col in self._df]
        self.dataset_semmap.datasetSchema.columns = cols

        # stats
        n_rows, n_cols = self._df.shape
        total_cells = n_rows * n_cols
        nnz = int(self._df.notna().to_numpy().sum())
        completeness = nnz / float(total_cells) if total_cells > 0 else 1.0
        self.dataset_semmap.summaryStatistics = SummaryStatistics(
            datasetCompleteness=completeness,
            numberOfRows=n_rows,
            numberOfColumns=n_cols,
        )

        return self.dataset_semmap

    def to_jsonld(self) -> Optional[Dict[str, Any]]:
        return self._df.semmap().to_jsonld()

    # ---- IO: Parquet with Arrow schema/field metadata ------------------------

    def to_parquet(self, path: str, *, index: bool = False, **pq_kwargs) -> None:
        """Write Parquet with semantics stored in Arrow schema and fields."""
        # 1) normalize columns for parquet storage
        df_store = {}
        for col in self._df.columns:
            s_acc = self._df[col].semmap
            s_norm = s_acc._ensure_storage_for_parquet()
            df_store[col] = s_norm
        pdf = pd.DataFrame(df_store, index=self._df.index if index else None)

        # 2) convert to Arrow table
        table = pa.Table.from_pandas(pdf, preserve_index=index)

        # 3) attach column semantics on each Field
        fields = []
        raw_columns = self._df.attrs.get("semmap_columns_raw")
        for field in table.schema:
            s_meta = None
            if isinstance(raw_columns, Mapping):
                candidate = raw_columns.get(field.name)
                if isinstance(candidate, Mapping):
                    s_meta = dict(candidate)
            if s_meta is None:
                s_meta = self._df[field.name].semmap.to_jsonld()
            fmeta = dict(field.metadata or {})
            if s_meta is not None:
                fmeta[_COLUMN_SEMMAP_KEY] = json.dumps(
                    s_meta, ensure_ascii=False
                ).encode("utf-8")
            fields.append(
                pa.field(
                    field.name, field.type, nullable=field.nullable, metadata=fmeta
                )
            )
        schema = pa.schema(fields)

        # 4) attach dataset semantics on Schema
        schema_meta = dict(schema.metadata or {})
        d_meta = self.to_jsonld()
        if d_meta is not None:
            schema_meta[_DATASET_SEMMAP_KEY] = json.dumps(
                d_meta, ensure_ascii=False
            ).encode("utf-8")
        schema = schema.with_metadata(schema_meta)

        # 5) write parquet
        pq.write_table(
            pa.Table.from_arrays(
                [table.column(i) for i in range(table.num_columns)], schema=schema
            ),
            path,
            **pq_kwargs,
        )

    @staticmethod
    def read_parquet(
        path: str, *, convert_pint: bool = True, **pq_kwargs
    ) -> pd.DataFrame:
        """Read Parquet and restore semantics + pint units."""
        table = pq.read_table(path, **pq_kwargs)
        schema = table.schema

        # Restore DataFrame
        df = table.to_pandas(types_mapper=None)  # leave as numeric/category

        # Restore dataset semantics
        if schema.metadata and _DATASET_SEMMAP_KEY in schema.metadata:
            df.semmap.from_jsonld(json.loads(
                schema.metadata[_DATASET_SEMMAP_KEY].decode("utf-8")
            ), convert_pint=convert_pint)

        # Restore column semantics, and optionally pint dtypes
        for i, field in enumerate(schema):
            name = field.name
            if field.metadata and _COLUMN_SEMMAP_KEY in field.metadata:
                col_jsonld = json.loads(
                    field.metadata[_COLUMN_SEMMAP_KEY].decode("utf-8")
                )
                df[name].semmap.from_jsonld(col_jsonld, convert_pint=convert_pint)
                if convert_pint:
                    SemMapFrameAccessor._coerce_column_to_pint(df, name, col_jsonld)

        return df



    @staticmethod
    def _coerce_column_to_pint(df: pd.DataFrame, column_name: str, col_jsonld: Mapping[str, Any]) -> None:
        """Best-effort conversion of a dataframe column to pint dtype.

        Args:
            df: Dataframe containing the target column.
            column_name: Name of the column to convert.
            col_jsonld: Column metadata payload.
        """

        col_prop = col_jsonld.get("columnProperty") or col_jsonld.get("dsv:columnProperty") or {}
        unit_text = col_prop.get("unitText") or col_prop.get("schema:unitText")
        has_unit = col_prop.get("hasUnit") or col_prop.get("qudt:hasUnit") or {}
        ucum_code = None
        if isinstance(has_unit, Mapping):
            ucum_code = has_unit.get("ucumCode") or has_unit.get("qudt:ucumCode")

        candidate_units: List[str] = []
        if isinstance(unit_text, str) and unit_text.strip():
            candidate_units.append(unit_text.strip())
        if isinstance(ucum_code, str) and ucum_code.strip():
            ucum_clean = ucum_code.strip()
            candidate_units.append(ucum_clean)
            candidate_units.append(ucum_clean.replace("[", "").replace("]", ""))

        deduped_candidates: List[str] = []
        for candidate in candidate_units:
            if candidate and candidate not in deduped_candidates:
                deduped_candidates.append(candidate)

        for candidate in deduped_candidates:
            try:
                df[column_name] = df[column_name].astype(f"pint[{candidate}]")
                return
            except Exception:
                continue

    # ---- External metadata loader -------------------------------------------

    def from_jsonld(
        self,
        metadata: str | dict[str, Any],
        *,
        convert_pint: bool = True,
    ) -> "SemMapFrameAccessor":
        """Attach dataset metadata and column schema from a JSON object."""
        # Load dict if given a path
        if isinstance(metadata, str):
            with open(metadata, "r", encoding="utf-8") as f:
                meta_jsonld = json.load(f)
        else:
            meta_jsonld = metadata

        if hasattr(meta_jsonld, "to_jsonld"):
            meta_jsonld = meta_jsonld.to_jsonld()

        # Attach dataset semantics verbatim (round-trip equality)
        self.dataset_semmap = Metadata.from_jsonld(meta_jsonld)

        # Apply per-column metadata if present
        schema_json = (
            (meta_jsonld or {}).get("datasetSchema")
            or (meta_jsonld or {}).get("dsv:datasetSchema")
            or {}
        )
        if hasattr(schema_json, "to_jsonld"):
            schema_json = schema_json.to_jsonld()
        cols = []
        if isinstance(schema_json, Mapping):
            cols = (schema_json.get("columns") or schema_json.get("dsv:column") or [])
        by_name = {
            c.get("name"): c for c in cols if isinstance(c, dict) and "name" in c
        }
        self._df.attrs["semmap_columns_raw"] = by_name

        for name, col_jsonld in by_name.items():
            if name in self._df.columns:
                self._df[name].semmap.from_jsonld(col_jsonld, convert_pint=convert_pint)
                if convert_pint:
                    self._coerce_column_to_pint(self._df, name, col_jsonld)

        return self

import pandas as pd

from semsynth import downstream_fidelity as dfid
from semsynth.codebook import Codebook


def _meta_with_columns(columns):
    return {
        "dsv:datasetSchema": {
            "dsv:column": columns,
        }
    }


def test_categorical_levels_no_missing_reference():
    meta = _meta_with_columns(
        [
            {
                "schema:name": "sex",
                "dsv:summaryStatistics": {"dsv:statisticalDataType": "dsv:NominalDataType"},
                "dsv:columnProperty": {
                    "dsv:hasCodeBook": {
                        "skos:hasTopConcept": [
                            {"skos:notation": "male"},
                            {"skos:notation": "female"},
                        ]
                    }
                },
            },
            {
                "schema:name": "outcome",
                "dsv:summaryStatistics": {"dsv:statisticalDataType": "dsv:NominalDataType"},
            },
        ]
    )
    df_real = pd.DataFrame(
        {
            "sex": ["female", "female", "male", "male", "female", "male", "female", "male"],
            "outcome": [0, 1, 0, 1, 0, 1, 0, 0],
        }
    )
    df_synth = pd.DataFrame(
        {
            "sex": ["female", "male", "male", "female", "female", "male", "female", "male"],
            "outcome": [1, 0, 1, 0, 1, 0, 0, 1],
        }
    )

    result = dfid.compute_downstream(df_real, df_synth, meta, target="outcome")
    assert result.get("skipped_reason") in (None, "no_predictors")


def test_intercept_only_when_no_predictors():
    meta = _meta_with_columns(
        [
            {
                "schema:name": "target",
                "dsv:summaryStatistics": {"dsv:statisticalDataType": "dsv:NominalDataType"},
            }
        ]
    )
    df = pd.DataFrame({"target": [0, 1, 0]})
    formula = dfid.auto_formula(df, meta, dfid.DownstreamConfig(), "target")
    assert formula == "target ~ 1"


def test_screen_terms_returns_intercept_on_design_error():
    meta = _meta_with_columns(
        [
            {
                "schema:name": "y",
                "dsv:summaryStatistics": {"dsv:statisticalDataType": "dsv:NominalDataType"},
            }
        ]
    )
    df = pd.DataFrame({"y": [1, 0, 1]})
    result = dfid.compute_downstream(df, df, meta, target="y")
    assert result.get("skipped_reason") is not None


def test_imputation_failure_is_caught():
    meta = _meta_with_columns(
        [
            {
                "schema:name": "all_missing",
                "dsv:summaryStatistics": {"dsv:statisticalDataType": "dsv:NumericalDataType"},
            },
            {
                "schema:name": "target",
                "dsv:summaryStatistics": {"dsv:statisticalDataType": "dsv:NominalDataType"},
            },
        ]
    )
    df_real = pd.DataFrame({"all_missing": [float("nan")] * 3, "target": [0, 1, 0]})
    df_synth = pd.DataFrame({"all_missing": [float("nan")] * 3, "target": [1, 0, 1]})

    result = dfid.compute_downstream(df_real, df_synth, meta, target="target")
    assert "skipped_reason" in result
    assert result["compare"] is None


def test_multiclass_targets_supported():
    meta = _meta_with_columns(
        [
            {
                "schema:name": "color",
                "dsv:summaryStatistics": {"dsv:statisticalDataType": "dsv:NominalDataType"},
                "dsv:columnProperty": {
                    "dsv:hasCodeBook": {
                        "skos:hasTopConcept": [
                            {"skos:notation": "red"},
                            {"skos:notation": "green"},
                            {"skos:notation": "blue"},
                        ]
                    }
                },
            },
            {
                "schema:name": "length",
                "dsv:summaryStatistics": {"dsv:statisticalDataType": "dsv:NumericalDataType"},
            },
        ]
    )
    df_real = pd.DataFrame(
        {
            "color": ["red", "green", "blue", "red", "green", "blue"],
            "length": [1.0, 2.0, 3.0, 1.5, 2.5, 3.5],
        }
    )
    df_synth = pd.DataFrame(
        {
            "color": ["red", "red", "green", "blue", "green", "blue"],
            "length": [1.1, 1.2, 2.1, 3.1, 2.6, 3.4],
        }
    )
    result = dfid.compute_downstream(df_real, df_synth, meta, target="color")
    assert result.get("skipped_reason") is None
    assert result["compare"] is not None


def test_numeric_codes_match_declared_text_codes():
    meta = Codebook(
        {"columns": [{"name": "y", "level": "nominal", "values": [{"code": "0"}, {"code": "1"}]}, {"name": "x"}]})
    df = pd.DataFrame({"y": [0, 1, 2, 0], "x": [0.1, 0.2, 0.3, 0.4]})
    coerced = dfid._coerce_frame(df, meta)
    assert list(coerced["y"].astype(str)) == ["0", "1", "2", "0"]
    meta.profile["columns"][0]["closed"] = True
    assert dfid._coerce_frame(df, meta)["y"].isna().sum() == 1

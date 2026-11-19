"""The scorecard and the small report pieces that read the evaluation files."""

from __future__ import annotations

from pathlib import Path

from semsynth.backends.pybnesian import graphml_text
from semsynth.models import ModelRun
from semsynth.report_scorecard import (
    build_scorecard,
    citation_text,
    documentation_items,
    joint_items,
    scorecard_note,
    scorecard_rows,
    structure_summary,
)


def _run(name: str, metrics: dict, baselines: dict | None = None) -> ModelRun:
    return ModelRun(
        name=name,
        backend="b",
        run_dir=Path("."),
        synthetic_csv=Path("s.csv"),
        per_variable_csv=None,
        metrics_json=None,
        metrics=metrics,
        umap_png=None,
        manifest={},
        privacy_json=None,
        baselines_metrics=baselines or {},
    )


def _cv(synthetic: float) -> dict:
    cell = lambda mean, lo, hi: {"n": 5, "mean": mean, "interval": [lo, hi]}  # noqa: E731
    return {
        "folds": 5,
        "train_rows": 80,
        "test_rows": 20,
        "scores": {
            "synthetic": {"disc_jsd_mean": cell(synthetic, 0.05, 0.2), "utility": cell(0.7, 0.6, 0.8)},
            "independent_marginals": {"disc_jsd_mean": cell(0.12, 0.05, 0.2), "utility": cell(0.5, 0.4, 0.6)},
            "real_sample": {"disc_jsd_mean": cell(0.1, 0.05, 0.15), "utility": cell(0.8, 0.7, 0.9)},
        },
    }


def test_the_scorecard_has_the_floor_each_model_and_the_ceiling_in_one_row() -> None:
    rows = scorecard_rows([_run("m1", {"cv": _cv(0.11)}), _run("m2", {"cv": _cv(0.13)})])
    first = rows[0]
    assert first["Score"].startswith("Discrete") and first["Floor"] == "0.12 [0.05, 0.2]" and first["Ceiling"] == "0.1 [0.05, 0.15]"
    assert first["m1"] == "0.11 [0.05, 0.2]" and first["m2"] == "0.13 [0.05, 0.2]"
    assert any(r["Score"].startswith("Prediction") and r["Floor"] == "0.5 [0.4, 0.6]" for r in rows)
    table = build_scorecard([_run("m1", {"cv": _cv(0.11)})]) or ""
    assert "Floor (independent columns)" in table and "Ceiling (real rows)" in table
    assert "5 folds" in (scorecard_note([_run("m1", {"cv": _cv(0.11)})]) or "")


def test_a_single_split_is_shown_with_its_noise_range_and_without_folds() -> None:
    baselines = {
        "scores": {
            "synthetic": {"disc_jsd_mean": 0.2, "null": {"disc_jsd_mean": {"null_interval": [0.1, 0.3]}}},
            "real_sample": {"disc_jsd_mean": 0.1},
        }
    }
    (row,) = scorecard_rows([_run("m", {}, baselines)])
    assert row["m"] == "0.2 (noise 0.1 to 0.3)" and row["Ceiling"] == "0.1" and row["Floor"] == ""
    assert scorecard_note([_run("m", {})]) is None and build_scorecard([_run("m", {})]) is None


def test_the_structure_says_when_no_dependency_was_learned(tmp_path: Path) -> None:
    (tmp_path / "structure.graphml").write_text(graphml_text({"a": "CKDType", "b": "CKDType"}, []))
    assert "no dependencies" in (structure_summary(tmp_path) or "")
    (tmp_path / "structure.graphml").write_text(graphml_text({"a": "CKDType", "b": "CKDType"}, [("a", "b")]))
    assert "a → b" in (structure_summary(tmp_path) or "")
    (tmp_path / "structure.graphml").write_text("")
    assert structure_summary(tmp_path) is None


def test_a_schema_org_citation_is_text_and_not_a_dict() -> None:
    article = {
        "@type": "schema:ScholarlyArticle",
        "title": "Predicting seminal quality",
        "schema:author": ["D. Gil", "J. Girela"],
        "schema:isPartOf": "Expert systems",
        "schema:datePublished": 2012,
        "url": "https://example.org/p",
    }
    assert citation_text(article) == "D. Gil, J. Girela (2012). Predicting seminal quality. Expert systems. https://example.org/p"
    assert citation_text("Plain text") == "Plain text" and citation_text(None) is None


def test_documentation_is_one_item_per_line_and_joint_items_list_the_worst_pairs() -> None:
    assert documentation_items("a: one\n\n b: two ") == ["a: one", "b: two"]
    joint = {
        "pairwise": {"status": "ok", "n_pairs": 3, "tvd_mean": 0.2, "tvd_max": 0.4, "worst_pairs": [{"columns": ["x", "y"], "tvd": 0.4}]},
        "classifier": {"status": "not_applicable", "reason": "fewer than 30 rows per class"},
    }
    labels = [label for label, _ in joint_items(joint)]
    assert "Pair x and y" in labels and "Real-vs-synthetic classifier" in labels

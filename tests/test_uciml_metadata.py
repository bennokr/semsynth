"""Tests for the DCAT and DSV metadata that the UCI provider writes."""

from __future__ import annotations

import numpy as np

from semsynth.dataproviders.uciml import to_dcat_dsv


def _variables() -> list[dict[str, object]]:
    return [{"name": "age", "type": "Integer", "units": "years", "role": "Feature", "description": "Age"}]


def test_rows_come_from_num_instances() -> None:
    for count in (320, np.int64(320), 320.0):
        document = to_dcat_dsv({"name": "Gallstone", "num_instances": count, "variables": _variables()})
        assert document["summaryStatistics"]["numberOfRows"] == 320
        assert document["summaryStatistics"]["numberOfColumns"] == 1


def test_no_rows_without_num_instances() -> None:
    document = to_dcat_dsv({"name": "Gallstone", "variables": _variables()})
    assert "summaryStatistics" not in document

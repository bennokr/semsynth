from semsynth.result import SynthesisResult


def test_result_summary_omits_payloads():
    result = SynthesisResult(
        synthetic_data=[{"x": 1}],
        backend="example",
        learned_model={"large": "model"},
        parameters={"rows": 1},
        semantics={"computational_actions": {"x": "bounded"}},
    )

    summary = result.summary()

    assert summary["backend"] == "example"
    assert summary["parameters"] == {"rows": 1}
    assert "synthetic_data" not in summary
    assert "learned_model" not in summary

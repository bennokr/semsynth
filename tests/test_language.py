"""Language detection of text columns and the Faker locale that MetaSyn draws free text in."""

from __future__ import annotations

from types import SimpleNamespace

import linked_codebook
import pandas as pd
import pytest

from semsynth.codebook import Codebook, infer_profile
from semsynth.language import apply_free_text_locales, detector, faker_locale

needs_protocol = pytest.mark.skipif(
    not hasattr(linked_codebook, "infer_language"), reason="linked-codebook older than 0.10 has no language protocol"
)

DUTCH = [
    "Dit is een erg goede winkel met vriendelijk personeel en een nette sfeer.",
    "Het eten was lekker en de bediening was snel, we komen zeker nog eens terug.",
    "De kamer was schoon en rustig, maar het ontbijt had beter gekund voor deze prijs.",
    "Mooie locatie in het centrum, alles is op loopafstand en het personeel helpt graag.",
]


@pytest.mark.parametrize(
    ("tag", "locale"),
    [("nl", "nl_NL"), ("en", "en_US"), ("de", "de_DE"), ("nl-BE", "nl_BE"), ("nl_NL", "nl_NL"), ("fr", "fr_FR")],
)
def test_faker_locale_for_a_language_tag(tag: str, locale: str) -> None:
    assert faker_locale(tag) == locale


@pytest.mark.parametrize("tag", [None, "", "xx", "zxx"])
def test_faker_locale_is_none_without_a_matching_locale(tag: str | None) -> None:
    assert faker_locale(tag) is None


def test_detector_names_the_language_and_abstains_on_non_prose() -> None:
    pytest.importorskip("py3langid")
    detect = detector()
    assert detect is not None
    assert detect(DUTCH[0]) == "nl"
    assert detect("12345 678") is None
    assert detect("ok") is None


@needs_protocol
def test_infer_profile_records_the_language_of_a_prose_column() -> None:
    pytest.importorskip("py3langid")
    frame = pd.DataFrame({"review": DUTCH * 5, "score": list(range(20))})
    profile = infer_profile(frame)
    columns = {column["name"]: column for column in profile["columns"]}
    assert columns["review"].get("language") == "nl"
    assert "language" not in columns["score"]


def test_free_text_gets_the_locale_of_its_column_language() -> None:
    pytest.importorskip("metasyn")
    from metasyn.distribution import FreeTextDistribution

    text = FreeTextDistribution("en_US", 3, 6)
    other = SimpleNamespace(name="other", distribution=SimpleNamespace(locale="en_US"))
    frame = SimpleNamespace(meta_vars=[SimpleNamespace(name="review", distribution=text), other])
    codebook = Codebook.read({"columns": [{"name": "review", "language": "nl"}, {"name": "other", "language": "nl"}]})
    apply_free_text_locales(frame, codebook)
    assert text.locale == "nl_NL"
    assert text.fake.locales == ["nl_NL"]
    assert other.distribution.locale == "en_US"

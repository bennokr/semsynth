"""The IRIs of everything SemSynth publishes, and the file and folder names that go with them.

Every IRI is under one base, by default ``https://bennokr.github.io/semsynth/output/``, which is also where the output
folder is served, so an IRI that names a document is its URL. Nothing contains a space, a capital or a character that
needs escaping: names are slugs, and the human title stays in ``dct:title``.

=========================  ==================================================  ====================================
what                       IRI                                                 note
=========================  ==================================================  ====================================
catalog                    ``<base>#catalog``
dataset (the real one)     ``<base><dataset>/``                                the report page; the codebook describes it
codebook                   ``<base><dataset>/dataset.codebook.jsonld``         its columns are ``<dataset>/#column-<name>``
synthetic dataset          ``<base><dataset>/models/<model>/``                 one per model run
run                        ``<base><dataset>/models/<model>/#run``
file                       ``<base><dataset>/models/<model>/<file>``           the URL of the file is its IRI
measurement                ``<base><dataset>/models/<model>/#measurement-<metric>``
metric                     ``https://bennokr.github.io/semsynth/metric/<id>``  shared by all datasets
=========================  ==================================================  ====================================

The identity of a thing is its IRI, whether or not the host still serves it. The base is one setting
(``PipelineConfig.iri_base``) so that it can move, for example to a w3id.org address that redirects here.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import quote

SITE = "https://bennokr.github.io/semsynth/"
DEFAULT_BASE = SITE + "output/"
CODEBOOK_FILE = "dataset.codebook.jsonld"


def slug(text: object, fallback: str = "dataset") -> str:
    """Lower-case letters, digits and single hyphens: ``"Heart Disease (UCI)"`` becomes ``"heart-disease-uci"``."""
    ascii_text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-") or fallback


@dataclass(frozen=True)
class Iris:
    """The IRIs under one base; build one with the base of the run and ask it for what you need."""

    base: str = DEFAULT_BASE

    def __post_init__(self) -> None:
        if not self.base.endswith("/"):
            object.__setattr__(self, "base", self.base + "/")

    @property
    def catalog(self) -> str:
        return f"{self.base}#catalog"

    def dataset(self, name: object) -> str:
        return f"{self.base}{slug(name)}/"

    def codebook(self, name: object) -> str:
        return self.dataset(name) + CODEBOOK_FILE

    def model(self, name: object, model: object) -> str:
        return f"{self.dataset(name)}models/{slug(model, 'model')}/"

    def run(self, name: object, model: object) -> str:
        return self.model(name, model) + "#run"

    def file(self, name: object, model: object, filename: str) -> str:
        return self.model(name, model) + quote(filename)

    def distribution(self, name: object, model: object, filename: str) -> str:
        return f"{self.model(name, model)}#distribution-{slug(filename, 'file')}"

    @staticmethod
    def metric(metric_id: str) -> str:
        return f"{SITE}metric/{quote(metric_id)}"

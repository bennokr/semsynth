#!/usr/bin/env python3
"""Check that the built reports hold what the site needs: python scripts/check_output.py output

A metric that is skipped (a missing extra) is recorded in its file, not raised, so a build that looks complete can lack the
privacy scores or the references. This reads the files. Only the standard library is used.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import unquote


def _nodes(value: object):  # type: ignore[no-untyped-def]
    """Every dictionary inside a JSON document."""
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _nodes(item)
    elif isinstance(value, list):
        for item in value:
            yield from _nodes(item)


def missing_downloads(output: Path) -> list[str]:
    """The files that the catalog offers for download (``dcat:downloadURL``) that the output does not have."""
    document = json.loads((output / "catalog.json").read_text(encoding="utf-8"))
    nodes = list(_nodes(document))
    base = next((n["@id"][: -len("#catalog")] for n in nodes if str(n.get("@id", "")).endswith("#catalog")), None)
    if base is None:
        return ["catalog.json has no catalog node"]
    urls = [n["@id"] for node in nodes for n in [node.get("dcat:downloadURL")] if isinstance(n, dict) and "@id" in n]
    return [f"the catalog offers {url}, which is not in the output" for url in urls if url.startswith(base) and not (output / unquote(url[len(base):])).is_file()]


def problems(output: Path) -> list[str]:
    found: list[str] = []
    if not (output / "catalog.json").is_file():
        found.append("catalog.json is missing")
    if not (output / "index.html").is_file():
        found.append("index.html is missing")
    pickles = sorted(output.rglob("*.pickle")) + sorted(output.rglob("*.pkl")) if output.is_dir() else []
    found += [f"{p.relative_to(output)} is a pickle: loading one can run code, so it is not published" for p in pickles[:5]]
    if (output / "catalog.json").is_file():
        found += missing_downloads(output)
    datasets = sorted(p for p in output.iterdir() if p.is_dir() and (p / "dataset.codebook.jsonld").is_file()) if output.is_dir() else []
    if not datasets:
        return [*found, "no dataset has a codebook"]
    for dataset in datasets:
        runs = sorted((dataset / "models").glob("*/")) if (dataset / "models").is_dir() else []
        if not runs:
            found.append(f"{dataset.name}: no model was run")
        for run in runs:
            for name in ("metrics.privacy.json", "metrics.baselines.json", "provenance.json"):
                path = run / name
                if not path.is_file():
                    found.append(f"{run.relative_to(output)}: {name} is missing")
                elif name == "metrics.privacy.json" and json.loads(path.read_text(encoding="utf-8")).get("status", "ok") != "ok":
                    found.append(f"{run.relative_to(output)}: privacy metrics skipped or failed")
    return found


def main(argv: list[str]) -> int:
    output = Path(argv[1]) if len(argv) > 1 else Path("output")
    found = problems(output)
    for line in found:
        print(f"error: {line}", file=sys.stderr)
    if not found:
        print(f"{output}: ok")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

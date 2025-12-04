#!/usr/bin/env python3
"""
Build an open medical terminology proxy from Wikidata.

Output: `codes.tsv` with columns::

    system    code    label    synonyms

- ``system``: WD
- ``code``: the Wikidata QID (e.g. ``Q12136``)
- ``label``: English preferred label
- ``synonyms``: semicolon-joined set of English alt labels and descriptions

Run:

    python build_wikidata_medical_codes_table.py

Then:

  sqlite-utils insert terminology.db codes codes.tsv --tsv
  sqlite-utils enable-fts terminology.db codes label synonyms --create-triggers
"""

import csv
import time
from pathlib import Path
from typing import Dict, List, Tuple

import requests

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "WikidataMedicalProxy/0.1 (b.b.kruit@amsterdamumc.nl)"

# Safety limits to reduce timeouts – tune these as needed
DEFAULT_LIMIT_PER_SYSTEM = 50000

# Your simplified query template
SPARQL_TEMPLATE = """
PREFIX wd:   <http://www.wikidata.org/entity/>
PREFIX wdt:  <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX schema: <http://schema.org/>
SELECT
  ("%(system)s" AS ?system)
  ?qid
  ?labelEn
  (SAMPLE(?descEn) AS ?descriptionEn)
  (GROUP_CONCAT(DISTINCT ?altEn; separator="; ") AS ?altLabels)
WHERE {
  {
    ?item wdt:P31/wdt:P279* %(root)s .
  }
  UNION
  {
    ?item wdt:P279/wdt:P279* %(root)s .
  }
  ?item wikibase:sitelinks ?links .
  FILTER(?links > 0)

  # English label for display
  ?item rdfs:label ?labelEn .
  FILTER (LANG(?labelEn) = "en")

  OPTIONAL {
    ?item schema:description ?descEn .
    FILTER (LANG(?descEn) = "en")
  }
  OPTIONAL {
    ?item skos:altLabel ?altEn .
    FILTER (LANG(?altEn) = "en")
  }

  # Turn the Q-ID into a simple numeric/slug code if desired
  BIND(STRAFTER(STR(?item), "entity/") AS ?qid)
}
GROUP BY ?system ?qid ?labelEn
"""

# Systems and their root classes
ROOTS: List[Tuple[str, str]] = [
    ("DISEASE", "wd:Q12136"),   # disease
    ("SYMPTOM", "wd:Q169872"),  # symptom
    ("PROCEDURE", "wd:Q796194"),  # medical procedure
    ("TEST", "wd:Q2671652"),    # medical test
    ("SIGN", "wd:Q1441305"),    # clinical sign
]


def run_sparql(query: str) -> Dict:
    """Run a SPARQL query and return the JSON result."""
    headers = {"User-Agent": USER_AGENT}
    params = {"query": query, "format": "json"}
    resp = requests.get(ENDPOINT, headers=headers, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_system(system: str, root: str, limit: int) -> Dict[Tuple[str, str], Dict]:
    """
    Run the query for one system/root.
    Returns a dict keyed by (system, qid) to deduplicate rows.
    """
    query = SPARQL_TEMPLATE % {"system": system, "root": root}
    if limit:
        query = query + f"\nLIMIT {limit}\n"

    data = run_sparql(query)
    bindings = data.get("results", {}).get("bindings", [])

    rows: Dict[Tuple[str, str], Dict] = {}
    for b in bindings:
        qid = b["qid"]["value"]          # e.g. "Q12136"
        label = b["labelEn"]["value"]    # English label

        key = (system, qid)
        if key not in rows:
            rows[key] = {
                "system": system,
                "code": qid,
                "label": label,
                "synonyms": set(),
                "description": b.get("descriptionEn", {}).get("value", "").strip(),
            }
        # Collect preferred label, alt labels, and description as synonyms
        rows[key]["synonyms"].add(label)
        alt_labels = b.get("altLabels", {}).get("value", "")
        if alt_labels:
            for alt in alt_labels.split("; "):
                alt = alt.strip()
                if alt:
                    rows[key]["synonyms"].add(alt)
        if rows[key]["description"]:
            rows[key]["synonyms"].add(rows[key]["description"])

    return rows


def write_codes_tsv(rows: Dict[Tuple[str, str], Dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["system", "code", "label", "synonyms"])
        all_rows = set()
        for key in sorted(rows):
            row = rows[key]
            synonyms_str = "; ".join(sorted(row["synonyms"]))
            all_rows.add((row["system"], row["code"], row["label"], synonyms_str))
        for row in all_rows:
            writer.writerow(row)


def main() -> None:
    out_path = Path("codes.tsv")
    all_rows: Dict[Tuple[str, str], Dict] = {}

    for system, root in ROOTS:
        print(f"Fetching {system} from {root} ...")
        try:
            rows = fetch_system("WD", root, DEFAULT_LIMIT_PER_SYSTEM)
        except Exception as e:
            print(f"Error fetching {system}: {e}")
            continue

        all_rows.update(rows)
        # Be polite to the WDQS service
        time.sleep(2)

    print(f"Collected {len(all_rows)} items total")
    write_codes_tsv(all_rows, out_path)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

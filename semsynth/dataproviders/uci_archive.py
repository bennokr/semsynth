"""Download a UCI ML dataset from its archive, for datasets that ``ucimlrepo`` cannot import.

``ucimlrepo`` needs a ``data_url`` in the UCI API, which some datasets (such as 1150, Gallstone) lack.
Their files are still published as a zip archive, sometimes with another zip or a spreadsheet inside.
Spreadsheets are read with the standard library, because some (Gallstone's) are Strict Open XML, which
openpyxl does not read.

Run as a script to fill the cache: ``python -m semsynth.dataproviders.uci_archive 1150``.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from typing import Any, Dict, Iterator, List, Tuple
from xml.etree import ElementTree

import pandas as pd
import requests

API_URL = "https://archive.ics.uci.edu/api/dataset"
ARCHIVE_URL = "https://archive.ics.uci.edu/static/public/{id}/{slug}.zip"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(node: ElementTree.Element, name: str) -> List[ElementTree.Element]:
    return [child for child in node.iter() if _local(child.tag) == name]


def _cell(cell: ElementTree.Element, shared: List[str]) -> Any:
    kind = cell.get("t")
    value = next((child.text for child in cell if _local(child.tag) == "v"), None)
    if kind == "inlineStr":
        return "".join(t.text or "" for t in _children(cell, "t"))
    if value is None:
        return None
    if kind == "s":
        return shared[int(value)]
    if kind in ("str", "e", "d"):
        return value
    number = float(value)
    return int(number) if number.is_integer() else number


def read_xlsx(payload: bytes) -> pd.DataFrame:
    """The first worksheet of an .xlsx file, with its first row as header. Namespaces are ignored."""
    with zipfile.ZipFile(io.BytesIO(payload)) as book:
        names = book.namelist()
        shared: List[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(book.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in _children(si, "t")) for si in _children(root, "si")]
        sheet = sorted(name for name in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))[0]
        root = ElementTree.fromstring(book.read(sheet))
    rows: List[Dict[str, Any]] = []
    for row in _children(root, "row"):
        cells = {re.sub(r"\d", "", cell.get("r", "")): _cell(cell, shared) for cell in _children(row, "c")}
        rows.append(cells)
    if not rows:
        return pd.DataFrame()
    header = rows[0]
    columns = sorted(header, key=lambda ref: (len(ref), ref))
    return pd.DataFrame([[row.get(ref) for ref in columns] for row in rows[1:]], columns=[header[ref] for ref in columns])


_READERS = {
    ".csv": lambda payload: pd.read_csv(io.BytesIO(payload)),
    ".data": lambda payload: pd.read_csv(io.BytesIO(payload), header=None),
    ".xlsx": read_xlsx,
}


def fetch_metadata(dataset_id: int) -> Dict[str, Any]:
    """The metadata of a dataset from the UCI API, with its variables."""
    response = requests.get(API_URL, params={"id": dataset_id}, timeout=60)
    response.raise_for_status()
    return response.json()["data"]


def _tables(payload: bytes) -> Iterator[Tuple[str, bytes]]:
    """Every table file in a zip archive, also inside zip archives in it."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in archive.namelist():
            data = archive.read(name)
            if name.lower().endswith(".zip"):
                yield from _tables(data)
            elif any(name.lower().endswith(suffix) for suffix in _READERS):
                yield name, data


def _read(name: str, payload: bytes) -> pd.DataFrame:
    suffix = next(suffix for suffix in _READERS if name.lower().endswith(suffix))
    return _READERS[suffix](payload)


def fetch_frame(dataset_id: int) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """The table of a dataset and its API metadata.

    Of the tables in the archive, the first that has every variable as a column is used, or else the largest.
    """
    metadata = fetch_metadata(dataset_id)
    slug = str(metadata["repository_url"]).rstrip("/").rsplit("/", 1)[-1]
    url = ARCHIVE_URL.format(id=dataset_id, slug=slug)
    logging.info("Downloading UCI ML archive %s", url)
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    frames = [(name, _read(name, data)) for name, data in _tables(response.content)]
    if not frames:
        raise ValueError(f"No table found in {url}")
    names = {str(variable["name"]) for variable in metadata.get("variables") or []}
    complete = [frame for _, frame in frames if names and names <= set(map(str, frame.columns))]
    frame = complete[0] if complete else max((frame for _, frame in frames), key=len)
    return frame, metadata


if __name__ == "__main__":
    import pathlib
    import sys

    from ..datasets import _UCIML_CACHE_DIR
    from .uciml import load_uciml_by_id

    logging.basicConfig(level=logging.INFO)
    for raw in sys.argv[1:]:
        payload = load_uciml_by_id(int(raw), pathlib.Path(_UCIML_CACHE_DIR))
        print(f"{raw}: {payload.spec.name}, {payload.frame.shape[0]} rows, {payload.frame.shape[1]} columns")

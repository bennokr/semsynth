"""Tests for reading UCI archives without ucimlrepo."""

import io
import zipfile

from semsynth.dataproviders.uci_archive import _tables, read_xlsx

STRICT = "http://purl.oclc.org/ooxml/spreadsheetml/main"


def _xlsx() -> bytes:
    """A minimal Strict Open XML workbook: shared strings, a number and an inline string."""
    sheet = (
        f'<worksheet xmlns="{STRICT}"><sheetData>'
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
        '<row r="2"><c r="A2"><v>50</v></c><c r="B2" t="inlineStr"><is><t>yes</t></is></c></row>'
        '<row r="3"><c r="A3"><v>2.5</v></c></row>'
        "</sheetData></worksheet>"
    )
    strings = f'<sst xmlns="{STRICT}"><si><t>Age</t></si><si><t>Status</t></si></sst>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as book:
        book.writestr("xl/worksheets/sheet1.xml", sheet)
        book.writestr("xl/sharedStrings.xml", strings)
    return buffer.getvalue()


def test_strict_workbook_is_read() -> None:
    df = read_xlsx(_xlsx())
    assert list(df.columns) == ["Age", "Status"]
    assert df["Age"].tolist() == [50, 2.5]
    assert df["Status"].tolist()[0] == "yes"


def test_tables_are_found_in_nested_archives() -> None:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr("dataset-uci.xlsx", _xlsx())
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr("dataset-uci.zip", inner.getvalue())
    assert [name for name, _ in _tables(outer.getvalue())] == ["dataset-uci.xlsx"]

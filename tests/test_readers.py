import io
import zipfile
import pytest
from scripts.generate_fixtures import xlsx_bytes
from xingcheng.readers import FileProblem, MAX_FILE_BYTES, read_workbook


@pytest.mark.parametrize(
    "data,name",
    [
        (b"", "a.xlsx"),
        (b"broken", "a.xlsx"),
        (b"broken", "a.xls"),
        (b"a", "a.pdf"),
        (b"\x00", "a.csv"),
        (b"\xff", "a.csv"),
        (b"PK\x03\x04", "a.csv"),
        (b"x" * (MAX_FILE_BYTES + 1), "a.csv"),
    ],
    ids=[
        "empty",
        "bad-xlsx",
        "bad-xls",
        "unsupported",
        "nul",
        "encoding",
        "binary-csv",
        "oversize",
    ],
)
def test_reject_bad_files(data, name):
    with pytest.raises(FileProblem):
        read_workbook(data, name)


def test_sheet_limit():
    with pytest.raises(FileProblem, match="50"):
        read_workbook(xlsx_bytes({str(i): [["x"]] for i in range(51)}), "a.xlsx")


def test_dimension_limit():
    from openpyxl import Workbook

    book = Workbook()
    book.active.cell(1000, 1000, "x")
    buffer = io.BytesIO()
    book.save(buffer)
    with pytest.raises(FileProblem, match="单元格"):
        read_workbook(buffer.getvalue(), "a.xlsx")


def test_zip_expansion_limit():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("large.xml", b"x" * (61 * 1024 * 1024))
    with pytest.raises(FileProblem, match="解压"):
        read_workbook(output.getvalue(), "a.xlsx")

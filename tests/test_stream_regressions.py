"""Exercise streamed imports with cursor-based column consumption."""

import os
from pathlib import Path
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

import numpy as N
import pytest
from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from veusz import document
from veusz.dataimport import simpleread
from veusz.dataimport.defn_twod import ImportParams2D, OperationDataImport2D
from veusz.dataimport.defn_nd import ImportParamsND
from veusz.document.commandinterface import CommandInterface


def test_simple_read_2d_keeps_rows_separate():
    reader = simpleread.SimpleRead2D("matrix", ImportParams2D())
    reader.readData(simpleread.StringStream("1 2\n3 4\n"))
    N.testing.assert_array_equal(reader.data, [[3, 4], [1, 2]])


def test_import_string_2d_headers_and_blank_separated_datasets():
    doc = document.Document()
    interface = CommandInterface(doc)
    interface.ImportString2D(
        ["first", "second"],
        "xrange 0 2\nyrange -1 1\n1 2\n3 4\n\n"
        "xcent 10 20\nycent 30 40\n5 6\n7 8\n")
    N.testing.assert_array_equal(doc.data["first"].data, [[3, 4], [1, 2]])
    assert doc.data["first"].xrange == (0.0, 2.0)
    assert doc.data["first"].yrange == (-1.0, 1.0)
    N.testing.assert_array_equal(doc.data["second"].data, [[7, 8], [5, 6]])
    xcent, ycent = doc.data["second"].getPixelCentres()
    N.testing.assert_array_equal(xcent, [10, 20])
    N.testing.assert_array_equal(ycent, [30, 40])


@pytest.mark.parametrize("locale, delimiter, rows, expected", [
    ("en_US", ",", "1,2\n3,4\n\n5,6\n7,8\n", [[3, 4], [1, 2]]),
    ("de_DE", ";", "1,5;2,5\n3,5;4,5\n\n5;6\n7;8\n",
     [[3.5, 4.5], [1.5, 2.5]]),
])
def test_csv_stream_two_datasets(tmp_path, locale, delimiter, rows, expected):
    source = tmp_path / "matrix.csv"
    source.write_text(rows, encoding="utf-8")
    doc = document.Document()
    doc.applyOperation(OperationDataImport2D(ImportParams2D(
        filename=str(source), datasetnames=["first", "second"], mode="csv",
        csvlocale=locale, csvdelimiter=delimiter)))
    N.testing.assert_array_equal(doc.data["first"].data, expected)
    N.testing.assert_array_equal(doc.data["second"].data, [[7, 8], [5, 6]])


@pytest.mark.parametrize("csv", [False, True])
def test_new_line_preserves_only_unconsumed_tokens(tmp_path, csv):
    if csv:
        source = tmp_path / "tokens.csv"
        source.write_text("1,2\n3,4\n", encoding="utf-8")
        stream = simpleread.CSVStream(str(source), ",", '"', "en_US", "utf_8")
    else:
        stream = simpleread.StringStream("1 2\n3 4\n")
    assert stream.newLine()
    assert stream.nextColumn() == "1"
    assert stream.newLine()
    assert stream.allColumns() == ["2", "3", "4"]
    assert len(stream.remainingline) == 3
    assert [stream.nextColumn() for _ in range(3)] == ["2", "3", "4"]
    assert stream.nextColumn() is None
    assert not stream.newLine()
    assert stream.allColumns() == []


def test_continuation_lines_and_comments_keep_matrix_rows():
    reader = simpleread.SimpleRead2D("matrix", ImportParams2D())
    reader.readData(simpleread.StringStream(
        "1 \\\n2 # first row\n3 \\\n4\n"))
    N.testing.assert_array_equal(reader.data, [[3, 4], [1, 2]])


def test_nd_stream_does_not_repeat_previous_rows():
    reader = simpleread.SimpleReadND("matrix", ImportParamsND())
    reader.readData(simpleread.StringStream("1 2\n3 4\n"))
    N.testing.assert_array_equal(reader.data, [[1, 2], [3, 4]])


@pytest.mark.parametrize("blocked", [False, True])
def test_automatic_descriptor_finishes_with_expected_columns(blocked):
    script = """
import sys
from veusz.dataimport.simpleread import SimpleRead, StringStream
reader = SimpleRead('')
reader.readData(StringStream('1 2\\n3 4\\n\\n5 6\\n7 8\\n'),
                useblocks=sys.argv[1] == 'True')
output = {}
reader.setOutput(output)
if sys.argv[1] == 'True':
    assert set(output) == {'col1_1', 'col2_1', 'col1_2', 'col2_2'}
    assert list(output['col1_1'].data) == [1, 3]
    assert list(output['col2_2'].data) == [6, 8]
else:
    assert set(output) == {'col1', 'col2'}
    assert list(output['col1'].data) == [1, 3, 5, 7]
    assert list(output['col2'].data) == [2, 4, 6, 8]
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(blocked)], capture_output=True, text=True,
        timeout=15, cwd=Path(__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr

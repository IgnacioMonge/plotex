"""Regression checks against real documents, imports and setting references."""

import os
from pathlib import Path
import stat
import subprocess
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

import pytest
from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from veusz import datasets, document, setting
from veusz.dataimport.base import ImportingError
from veusz.dataimport.defn_csv import ImportParamsCSV, OperationDataImportCSV
from veusz.document import doc as docmod, loader
from veusz.setting.reference import ReferenceBase

SAVE_MODES = ["vsz", pytest.param(
    "hdf5", marks=pytest.mark.skipif(docmod.h5py is None, reason="Missing h5py"))]

@pytest.fixture
def newdoc(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(loader, "_cacheDir", lambda: str(cache))
    return document.Document()


@pytest.mark.parametrize("mode", SAVE_MODES)
def test_failed_serialization_preserves_saved_file(newdoc, tmp_path, monkeypatch, mode):
    target = tmp_path / "saved"
    target.write_bytes(b"previous complete document")
    newdoc.filename = "previous-name.vsz"
    newdoc.setData("unsaved", datasets.Dataset([42.0]))
    before = set(tmp_path.iterdir())

    def fail_header(stream, kind):
        stream.write("partial new document")
        raise OSError("serialization failed")

    monkeypatch.setattr(newdoc, "_writeFileHeader", fail_header)
    with pytest.raises(OSError, match="serialization failed"):
        newdoc.save(str(target), mode)

    assert target.read_bytes() == b"previous complete document"
    assert newdoc.modified
    assert newdoc.filename == "previous-name.vsz"
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("mode", SAVE_MODES)
def test_failed_replace_preserves_modified_state(newdoc, tmp_path, monkeypatch, mode):
    target = tmp_path / "saved"
    target.write_bytes(b"original")
    newdoc.filename = "old-name.vsz"
    newdoc.setData("unsaved", datasets.Dataset([42.0]))
    before = set(tmp_path.iterdir())

    def fail_replace(source, destination):
        assert Path(source).parent == target.parent
        assert newdoc.modified
        raise PermissionError("replace denied")

    monkeypatch.setattr(docmod.os, "replace", fail_replace)
    with pytest.raises(PermissionError, match="replace denied"):
        newdoc.save(str(target), mode)

    assert target.read_bytes() == b"original"
    assert newdoc.modified
    assert newdoc.filename == "old-name.vsz"
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("mode", SAVE_MODES)
def test_atomic_save_roundtrip_preserves_links_and_permissions(newdoc, tmp_path, mode):
    csv = tmp_path / "input.csv"
    csv.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    newdoc.applyOperation(OperationDataImportCSV(ImportParamsCSV(
        filename=str(csv), headermode="1st", linked=True)))
    newdoc.makeDefaultDoc()
    target = tmp_path / ("saved.vsz" if mode == "vsz" else "saved.vszh5")
    target.write_bytes(b"original")
    target.chmod(stat.S_IREAD | stat.S_IWRITE)
    oldmode = stat.S_IMODE(target.stat().st_mode)
    newdoc.save(str(target), mode)

    assert newdoc.filename == str(target)
    assert not newdoc.modified
    assert stat.S_IMODE(target.stat().st_mode) == oldmode
    if mode == "vsz":
        commands = target.read_text(encoding="utf-8")
    else:
        with docmod.h5py.File(target, "r") as handle:
            commands = handle["Veusz/Document/document"][0].decode("utf-8")
    assert "ImportFileCSV('input.csv'" in commands
    assert str(tmp_path).replace("\\", "/") in commands.replace("\\\\", "/")

    loaded = document.Document()
    loaded.load(str(target), mode=mode)
    assert list(loaded.data["a"].data) == [1.0, 3.0]
    assert list(loaded.data["b"].data) == [2.0, 4.0]
    assert loaded.basewidget.getChild("page1") is not None


def test_loading_clone_and_nested_setdata_finish(tmp_path):
    source = tmp_path / "clone.vsz"
    source.write_text(
        "Add('page', name='page1')\nTo('/')\n"
        "CloneWidget('/page1', '/', 'page2')\nSetData('loaded', [1, 2])\n",
        encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    script = """
import sys
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from veusz import document, datasets
from veusz.document import loader
loader._cacheDir = lambda: sys.argv[2]
doc = document.Document()
doc.load(sys.argv[1])
assert doc.basewidget.getChild('page2') is not None
assert list(doc.data['loaded'].data) == [1, 2]
class Nested:
    def do(self, document):
        document.setData('nested', datasets.Dataset([3]))
doc.loading = True
doc.applyOperation(Nested())
assert list(doc.data['nested'].data) == [3]
assert doc._write_lock_depth == 0
assert doc._write_lock_holder is None
assert doc._render_lock.tryLockForRead(0)
doc._render_lock.unlock()
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(source), str(cache)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        timeout=20, env={**os.environ, "QT_QPA_PLATFORM": "minimal"})
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("preloaded", [False, True])
def test_import_rename_swap_preserves_datasets_and_undo(newdoc, tmp_path, preloaded):
    csv = tmp_path / "input.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")
    original = datasets.Dataset([99.0])
    newdoc.setData("a", original)
    operation = OperationDataImportCSV(ImportParamsCSV(
        filename=str(csv), headermode="1st", renames={"a": "b", "b": "a"}))
    if preloaded:
        operation.preloadImport()
    newdoc.applyOperation(operation)
    assert list(newdoc.data["a"].data) == [2.0]
    assert list(newdoc.data["b"].data) == [1.0]
    assert operation.outnames == ["a", "b"]
    newdoc.undoOperation()
    assert newdoc.data == {"a": original}
    newdoc.redoOperation()
    assert list(newdoc.data["a"].data) == [2.0]
    assert list(newdoc.data["b"].data) == [1.0]


@pytest.mark.parametrize("renames", [{"a": "b"}, {"a": "same", "b": "same"}])
def test_import_rejects_duplicate_destinations_before_document_changes(
        newdoc, tmp_path, renames):
    csv = tmp_path / "input.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")
    original = datasets.Dataset([99.0])
    newdoc.setData("a", original)
    operation = OperationDataImportCSV(ImportParamsCSV(
        filename=str(csv), headermode="1st", renames=renames))
    operation.preloadImport()
    operation.outcustoms = [["constant", "must_not_be_added", "42"]]
    definitions = list(newdoc.evaluate.def_definitions)
    with pytest.raises(ImportingError, match="Duplicate dataset name"):
        newdoc.applyOperation(operation)
    assert newdoc.data == {"a": original}
    assert newdoc.evaluate.def_definitions == definitions
    assert not newdoc.historyundo


def axis_settings(doc):
    doc.makeDefaultDoc()
    return [doc.resolveSettingPath(None, "/page1/graph1/" + path)
            for path in ("x/min", "y/min", "x/max", "y/max")]


@pytest.mark.parametrize("multiple", [False, True])
def test_real_setting_cycle_raises_resolve_exception(newdoc, multiple):
    a, b, _, _ = axis_settings(newdoc)
    a.set(setting.Reference(b.path))
    b.set(setting.ReferenceMultiple([a.path]) if multiple else setting.Reference(a.path))
    with pytest.raises(ReferenceBase.ResolveException):
        a.get()
    with pytest.raises(ReferenceBase.ResolveException):
        a.getReference().resolve(a)


def test_multiple_references_use_distance_and_skip_cycles(newdoc):
    a, b, c, d = axis_settings(newdoc)
    b.set(10.0)
    a.set(setting.ReferenceMultiple([b.path, d.path]))
    assert a.get() == 10.0  # A later default value does not override an explicit value.
    c.set(setting.Reference(d.path))
    d.set(20.0)
    a.set(setting.ReferenceMultiple([b.path, c.path]))
    assert a.get() == 10.0  # The closer setting wins over a later, longer chain.
    a.set(setting.ReferenceMultiple([b.path, d.path]))
    assert a.get() == 20.0  # Rightmost wins at the same distance.
    b.set(setting.Reference(a.path))
    a.set(setting.ReferenceMultiple([b.path, d.path]))
    assert a.get() == 20.0  # A cyclic alternative does not hide a valid link.


def test_stylesheet_cache_and_default_links_survive(newdoc):
    newdoc.makeDefaultDoc()
    width = newdoc.resolveSettingPath(None, "/page1/graph1/x/Line/width")
    reference = width.getReference()
    assert width.isDefault()
    destination = reference.resolve(width)
    assert reference.resolve(width) is destination
    destination.set("2pt")
    assert width.get() == "2pt"
    assert width.isDefault()
    destination.set(setting.Reference(width.path))
    with pytest.raises(ReferenceBase.ResolveException):
        width.get()

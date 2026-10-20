"""Equivalence and operation counts for document/import optimizations."""

from collections import Counter
import cProfile
import io
import pstats

import numpy as np
import pytest


@pytest.fixture
def doc(qapp, tmp_path, monkeypatch):
    from veusz import document, setting
    from veusz.document import loader

    monkeypatch.setitem(setting.transient_settings, "unsafe_mode", False)
    monkeypatch.setitem(setting.settingdb, "secure_dirs", [])
    monkeypatch.setattr(loader, "_cacheDir", lambda: str(tmp_path))
    monkeypatch.setattr(loader, "_HMAC_KEY", None)
    return document.Document()


@pytest.mark.parametrize("options, expected", [
    ({}, [[4, 5, 6], [1, 2, 3]]),
    ({"invertrows": True}, [[1, 2, 3], [4, 5, 6]]),
    ({"invertcols": True}, [[6, 5, 4], [3, 2, 1]]),
    ({"transpose": True}, [[4, 1], [5, 2], [6, 3]]),
    ({"invertrows": True, "invertcols": True, "transpose": True},
     [[3, 6], [2, 5], [1, 4]]),
])
def test_2d_row_orientation(qapp, options, expected):
    from veusz.dataimport.simpleread import SimpleRead2D, StringStream
    from veusz.dataimport.defn_twod import ImportParams2D

    reader = SimpleRead2D("matrix", ImportParams2D(**options))
    reader.readData(StringStream("1 2 3\n4 5 6\n"))
    np.testing.assert_array_equal(reader.data, expected)


def test_2d_grid_headers_and_descending_coordinates(qapp):
    from veusz.dataimport.simpleread import SimpleRead2D, StringStream
    from veusz.dataimport.defn_twod import ImportParams2D

    reader = SimpleRead2D("grid", ImportParams2D(gridatedge=True))
    reader.readData(StringStream("10 20\n30 1 2\n40 3 4\n"))
    np.testing.assert_array_equal(reader.data, [[1, 2], [3, 4]])
    np.testing.assert_array_equal(reader.xcent, [10, 20])
    np.testing.assert_array_equal(reader.ycent, [30, 40])

    reader = SimpleRead2D("descending", ImportParams2D())
    reader.readData(StringStream("xcent 30 20 10\nycent 40 30\n1 2 3\n4 5 6\n"))
    np.testing.assert_array_equal(reader.data, [[3, 2, 1], [6, 5, 4]])
    np.testing.assert_array_equal(reader.xcent, [10, 20, 30])
    np.testing.assert_array_equal(reader.ycent, [30, 40])


def test_2d_rows_do_not_use_front_insertions(qapp):
    from veusz.dataimport.simpleread import SimpleRead2D, StringStream
    from veusz.dataimport.defn_twod import ImportParams2D

    reader = SimpleRead2D("matrix", ImportParams2D())
    profile = cProfile.Profile()
    profile.runcall(reader.readData, StringStream("1 2\n" * 100))
    insertions = sum(value[0] for key, value in pstats.Stats(profile).stats.items()
                     if "'insert' of 'list' objects" in key[2])
    assert insertions == 0
    assert reader.data.shape == (100, 2)

def test_snapshot_retains_objects_without_serialization(doc, monkeypatch):
    from veusz import datasets
    from veusz.document import loader

    doc.setData("data", datasets.Dataset(np.arange(10_000, dtype=float)))
    original_context = doc.evaluate.context
    original_compiled = doc.evaluate.compiled
    original_paths = doc.evaluate.importpath
    original_paths.append("original")

    def forbid_serialization(*args, **kwargs):
        pytest.fail("Snapshot must not serialize the original document")

    monkeypatch.setattr(doc, "serializeToText", forbid_serialization)
    snapshot = loader._takeDocumentSnapshot(doc)
    assert snapshot["data"]["data"] is doc.data["data"]
    assert snapshot["basewidget"] is doc.basewidget
    assert snapshot["evaluate"]["context"] is original_context
    assert snapshot["evaluate"]["importpath"] is not original_paths

    doc.wipe()
    doc.evaluate.importpath.append("new")
    assert original_context
    assert snapshot["evaluate"]["compiled"] is original_compiled
    assert snapshot["evaluate"]["importpath"] == ["original"]
    assert doc.evaluate.context is not original_context
    assert doc.evaluate.compiled is not original_compiled


@pytest.mark.parametrize("trusted", [False, True])
def test_failed_load_restores_identity_links_customs_history_and_trust(
        doc, tmp_path, trusted):
    from veusz.dataimport.defn_csv import ImportParamsCSV, OperationDataImportCSV
    from veusz.document import loader, operations
    from veusz.document.commandinterface import CommandInterface

    doc.makeDefaultDoc()
    source = tmp_path / "linked.csv"
    source.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    doc.applyOperation(OperationDataImportCSV(ImportParamsCSV(
        filename=str(source), headermode="1st", linked=True)))
    doc.data["a"].tags.add("original-tag")
    interface = CommandInterface(doc)
    interface.AddCustom("definition", "scale(x)", "x*3")
    interface.AddCustom("constant", "original_value", "len(DATA('a'))")
    interface.AddCustom("color", "original_color", "#123456")
    if trusted:
        interface.AddCustom("import", "math", "sqrt")
    doc.evaluate.setSecurity(trusted)
    doc.evaluate.importpath[:] = ["original-path"]
    doc.filename = "original.vsz"
    width = doc.basewidget.settings.get("width")
    height = doc.basewidget.settings.get("height")
    oldheight = height.get()
    doc.applyOperation(operations.OperationSettingSet(width, "20cm"))
    doc.applyOperation(operations.OperationSettingSet(height, "16cm"))
    doc.undoOperation()
    original = {
        "root": doc.basewidget, "graph": doc.basewidget.getChild("page1").getChild("graph1"),
        "data": dict(doc.data), "link": doc.data["a"].linked,
        "context": doc.evaluate.context, "definitions": doc.evaluate.def_definitions,
        "imports": doc.evaluate.def_imports, "compiled": doc.evaluate.compiled,
        "colors": doc.evaluate.colors, "colormaps": doc.evaluate.colormaps,
        "undo": list(doc.historyundo), "redo": list(doc.historyredo),
        "changeset": doc.changeset, "modified": doc.modified, "locale": doc.locale.name(),
        "compatlevel": doc.compatlevel,
    }
    source.unlink()  # Rollback must not reimport even when the linked source vanished.
    failed = tmp_path / "failed.vsz"
    failed.write_text(
        "import math\nAdd('page', name='partial')\n"
        "SetCompatLevel(0)\nSet('englishlocale', True)\n"
        "AddCustom('constant', 'wrong', '999')\n"
        "SetData('bad', [1, 2], serr=[1])\n", encoding="utf-8")
    prompts = []
    wiped_roots = []
    doc.sigWiped.connect(lambda: wiped_roots.append(doc.basewidget))
    with pytest.raises(loader.LoadError):
        doc.load(str(failed), callbackunsafe=lambda: prompts.append(True) or True)
    assert prompts == [True]
    assert doc.basewidget is original["root"]
    assert doc.basewidget.getChild("page1").getChild("graph1") is original["graph"]
    assert wiped_roots[-1] is original["root"]
    assert interface.currentwidget is original["root"]
    assert doc.data.keys() == original["data"].keys()
    for name, dataset in original["data"].items():
        assert doc.data[name] is dataset
        assert dataset.document is doc
    assert doc.data["a"].linked is original["link"]
    assert doc.data["a"].tags == {"original-tag"}
    assert doc.evaluate.context is original["context"]
    assert doc.evaluate.def_definitions is original["definitions"]
    assert doc.evaluate.def_imports is original["imports"]
    assert doc.evaluate.compiled is original["compiled"]
    assert doc.evaluate.colors is original["colors"]
    assert doc.evaluate.colormaps is original["colormaps"]
    assert doc.evaluate.context["original_value"] == 2
    assert doc.evaluate.context["scale"](2) == 6
    assert "wrong" not in doc.evaluate.context
    assert doc.evaluate.importpath == ["original-path"]
    assert doc.evaluate.inSecureMode() is trusted
    assert ("memmap" in doc.evaluate.context) is trusted
    assert doc.filename == "original.vsz"
    assert doc.compatlevel == original["compatlevel"]
    assert doc.locale.name() == original["locale"]
    assert doc.changeset == original["changeset"]
    assert doc.modified == original["modified"]
    assert doc.historyundo == original["undo"]
    assert doc.historyredo == original["redo"]
    doc.redoOperation()
    assert height.get() == "16cm"
    doc.undoOperation()
    assert height.get() == oldheight
    doc.undoOperation()
    assert width.get() != "20cm"
    doc.redoOperation()
    assert width.get() == "20cm"


def test_default_serializer_still_roundtrips_data_and_widgets(doc):
    from veusz import datasets, document
    from veusz.document import loader

    doc.makeDefaultDoc()
    doc.setData("data", datasets.Dataset([1, 2]))
    serialized = io.StringIO()
    doc.serializeToText(serialized)
    assert "ImportString(" in serialized.getvalue()
    restored = document.Document()
    loader.executeScript(restored, "roundtrip", serialized.getvalue())
    np.testing.assert_array_equal(restored.data["data"].data, [1, 2])
    assert restored.basewidget.getChild("page1").getChild("graph1") is not None


@pytest.mark.parametrize("multiple, depth", [(False, 64), (True, 32)])
def test_each_reference_edge_is_resolved_once_per_read(doc, monkeypatch, multiple, depth):
    from veusz import setting

    settings = [setting.Float("perf%d" % i, 1.0) for i in range(depth + 1)]
    for value in settings:
        doc.basewidget.settings.add(value)
    for index, value in enumerate(settings[:-1]):
        path = settings[index + 1].name
        value.set(setting.ReferenceMultiple([path]) if multiple else setting.Reference(path))
    counts = Counter()
    original = setting.Reference._resolveDirect

    def counted(self, source):
        counts[id(source)] += 1
        return original(self, source)

    monkeypatch.setattr(setting.Reference, "_resolveDirect", counted)
    assert settings[0].get() == 1
    assert len(counts) == depth
    assert set(counts.values()) == {1}
    counts.clear()
    destination = settings[0].getReference().resolve(settings[0])
    assert destination is (settings[-1] if multiple else settings[1])
    assert len(counts) == depth
    assert set(counts.values()) == {1}
    settings[-1].set(2.0)
    assert settings[0].get() == 2.0  # No stale value survives into another read.


def test_reference_priority_cycles_signals_and_nested_multiple(doc):
    from veusz import setting
    from veusz.setting.reference import ReferenceBase

    values = [setting.Float(name, 0.0) for name in ("a", "b", "c", "d", "e")]
    for value in values:
        doc.basewidget.settings.add(value)
    a, b, c, d, e = values
    b.set(10.0)
    d.set(20.0)
    c.set(setting.Reference("d"))
    a.set(setting.ReferenceMultiple(["b", "c"]))
    assert a.get() == 10.0
    a.set(setting.ReferenceMultiple(["b", "d"]))
    assert a.get() == 20.0
    d.set(0.0)
    assert a.get() == 10.0
    d.set(20.0)
    b.set(setting.Reference("a"))
    assert a.get() == 20.0
    e.set(setting.ReferenceMultiple(["c"]))
    a.set(setting.ReferenceMultiple(["c", "e"]))
    assert a.get() == 20.0
    assert a.getReference().resolve(a) is d

    a.set(setting.Reference("c"))
    notifications = []
    a.setOnModified(lambda: notifications.append(True))
    d.set(30.0)
    assert notifications == [True]
    assert a.getReference().resolve(a) is c
    assert a.get() == 30.0
    d.set(setting.Reference("a"))
    with pytest.raises(ReferenceBase.ResolveException):
        a.get()


def test_stylesheet_resolution_revalidates_cached_target(doc):
    from veusz import setting
    from veusz.setting.reference import ReferenceBase

    doc.makeDefaultDoc()
    width = doc.resolveSettingPath(None, "/page1/graph1/x/Line/width")
    reference = width.getReference()
    target = reference.resolve(width)
    assert width.isDefault()
    target.set("2pt")
    assert width.get() == "2pt"
    assert width.isDefault()
    target.set(setting.Reference(width.path))
    with pytest.raises(ReferenceBase.ResolveException):
        width.get()

"""Regression tests for document execution, cache permissions and embedding."""
import json
import struct

import numpy as np
import pytest


@pytest.fixture
def doc(qapp, monkeypatch, tmp_path):
    from veusz import document, setting
    from veusz.document import loader

    monkeypatch.setitem(setting.transient_settings, "unsafe_mode", False)
    monkeypatch.setitem(setting.settingdb, "secure_dirs", [])
    monkeypatch.setattr(loader, "_cacheDir", lambda: str(tmp_path))
    monkeypatch.setattr(loader, "_HMAC_KEY", None)
    return document.Document()


@pytest.mark.parametrize("source", [
    "memmap('unused', dtype='uint8', mode='w+', shape=1)",
    "genfromtxt('unused')",
    "list(map(array([1]).tofile, ['unused']))",
    "array([1]).ctypes",
    "array([1]).ctypes._ctypes",
    "'{x}'.format",
    "a = array([1])",
    "class Hidden:\n    pass",
    "def hidden():\n    pass",
    "lambda x: x + 1",
])
def test_untrusted_code_rejects_io_and_callable_indirection(doc, source):
    from veusz.utils import safe_eval

    with pytest.raises(safe_eval.SafeEvalException):
        safe_eval.compileChecked(source, mode="exec")


def test_safe_numerical_context_and_dataset_expressions(doc):
    from veusz import datasets

    assert "memmap" not in doc.evaluate.context
    assert "genfromtxt" not in doc.evaluate.context
    doc.setData("x", datasets.Dataset([0., 1., 2.]))
    result = doc.evaluate.evalDatasetExpression("sin(x) + 2")
    np.testing.assert_allclose(result.data, np.sin([0., 1., 2.]) + 2)
    code = doc.evaluate.compileCheckedExpression("min(2, 3) + array([1, 2]).size")
    assert doc.evaluate.safeEvaluateCompiled(code) == 4


def test_safe_custom_functions_and_constants_load_without_trust(doc, tmp_path):
    path = tmp_path / "custom.vsz"
    path.write_text(
        "AddCustom('constant', 'scale', '2')\n"
        "AddCustom('definition', 'shift(x, y)', 'scale*x + y')\n"
        "AddCustom('function', 'curve(x)', 'shift(x, 3) + 1')\n"
        "SetData('x', [0, 1, 2])\n"
        "SetDataExpression('y', 'curve(x)')\n", encoding="utf-8")
    prompts = []
    doc.load(str(path), callbackunsafe=lambda: prompts.append(True) or False)
    assert prompts == []
    assert not doc.evaluate.inSecureMode()
    np.testing.assert_array_equal(doc.data["y"].data, [4, 6, 8])
    assert doc.evaluate.context["shift"](3, 4) == 10


@pytest.mark.parametrize("body", [
    "memmap(path, dtype='uint8', mode='w+', shape=1)",
    "genfromtxt(path)",
    "list(map(array([1]).tofile, [path]))",
    "__import__('os')",
])
def test_custom_function_rejects_unsafe_body(doc, tmp_path, body):
    from veusz.document.commandinterface import CommandInterface

    target = tmp_path / "must-not-exist"
    CommandInterface(doc).AddCustom("definition", "danger(path)", body)
    assert "danger" not in doc.evaluate.context
    assert doc.evaluate.compileCheckedExpression("danger(%r)" % str(target)) is None
    assert not target.exists()


@pytest.mark.parametrize("signature", ["bad(x y)", "bad(x, x)", "bad(x): injected()"])
def test_custom_function_rejects_invalid_signature(doc, signature):
    from veusz.document.commandinterface import CommandInterface

    CommandInterface(doc).AddCustom("definition", signature, "x + 1")
    assert "bad" not in doc.evaluate.context


def test_revoking_trust_keeps_only_safe_custom_functions(doc):
    from veusz.document.commandinterface import CommandInterface

    doc.evaluate.setSecurity(True)
    interface = CommandInterface(doc)
    interface.AddCustom("definition", "safe(x)", "x + 1")
    interface.AddCustom("definition", "unsafe(path)", "genfromtxt(path)")
    assert "unsafe" in doc.evaluate.context
    doc.evaluate.setSecurity(False)
    assert doc.evaluate.context["safe"](2) == 3
    assert "unsafe" not in doc.evaluate.context


def test_regular_document_loads_without_permission_prompt(doc, tmp_path):
    path = tmp_path / "regular.vsz"
    path.write_text("SetData('x', [1, 2, 3])\nAdd('page')\n", encoding="utf-8")
    prompts = []
    doc.load(str(path), callbackunsafe=lambda: prompts.append(True) or False)
    assert prompts == []
    np.testing.assert_array_equal(doc.data["x"].data, [1, 2, 3])
    assert doc.getNumberPages() == 1


def test_untrusted_file_cannot_write_a_file(doc, tmp_path):
    from veusz.document.loader import LoadError

    target = tmp_path / "must-not-exist"
    path = tmp_path / "io.vsz"
    path.write_text(
        "memmap(%r, dtype='uint8', mode='w+', shape=1)\n" % str(target),
        encoding="utf-8",
    )
    with pytest.raises(LoadError, match="Unsafe command"):
        doc.load(str(path), callbackunsafe=lambda: False)
    assert not target.exists()


def test_cached_code_does_not_reuse_previous_permission(doc, tmp_path):
    from veusz.document.loader import LoadError

    path = tmp_path / "permission.vsz"
    path.write_text("import math\nSetData('x', [math.sqrt(4)])\n", encoding="utf-8")
    prompts = []
    doc.load(str(path), callbackunsafe=lambda: prompts.append(True) or True)
    assert prompts == [True]
    assert doc.data["x"].data[0] == 2
    with pytest.raises(LoadError, match="Unsafe command"):
        doc.load(str(path), callbackunsafe=lambda: prompts.append(False) or False)
    assert prompts == [True, False]
    assert doc.data["x"].data[0] == 2


def test_revoking_trust_invalidates_compiled_expressions(doc):
    expr = "array([1]).tolist()"
    doc.evaluate.setSecurity(True)
    assert doc.evaluate.compileCheckedExpression(expr) is not None
    doc.evaluate.setSecurity(False)
    assert doc.evaluate.compileCheckedExpression(expr) is None
    assert "memmap" not in doc.evaluate.context


@pytest.mark.parametrize("contents", [b"not HDF5", None])
def test_bad_hdf5_restores_existing_document(doc, tmp_path, contents):
    h5py = pytest.importorskip("h5py")
    from veusz import datasets
    from veusz.document.loader import LoadError

    doc.setData("previous", datasets.Dataset([42]))
    doc.filename = "original.vsz"
    path = tmp_path / "broken.vszh5"
    if contents is not None:
        path.write_bytes(contents)
    else:
        with h5py.File(path, "w") as f:
            group = f.create_group("Veusz")
            group.attrs["vsz_format"] = 1
            group.attrs["vsz_version"] = "1.7.0"
    with pytest.raises(LoadError):
        doc.load(str(path), mode="hdf5")
    assert doc.filename == "original.vsz"
    assert doc.data["previous"].data[0] == 42
    assert doc.isModified()


def test_embed_serializes_numpy_request(monkeypatch):
    from veusz.embed import Embedded

    response = json.dumps({"result": None}).encode()

    class Socket:
        sent = b""
        received = struct.pack("<I", len(response)) + response

        def send(self, data):
            self.sent += data
            return len(data)

        def recv(self, size):
            out, self.received = self.received[:size], self.received[size:]
            return out

    sock = Socket()
    monkeypatch.setattr(Embedded, "serv_socket", sock)
    monkeypatch.setattr(Embedded, "cmdlen", 4, raising=False)
    Embedded.sendCommand((0, "SetData", ("x", np.arange(3)), {"serr": np.float32(.5)}))
    size = struct.unpack("<I", sock.sent[:4])[0]
    payload = json.loads(sock.sent[4:])
    assert size == len(sock.sent) - 4
    assert payload == [0, "SetData", ["x", [0, 1, 2]], {"serr": .5}]
    with pytest.raises(TypeError):
        Embedded.sendCommand((0, "SetData", ("x", object()), {}))

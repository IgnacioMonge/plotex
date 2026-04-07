##############################################################################
"""JSON data import for Veusz/Plotex.

Supports:
 - Array of objects: [{"x": 1, "y": 2}, {"x": 3, "y": 4}]
 - Object of arrays: {"x": [1, 3], "y": [2, 4]}
 - Nested paths with dot notation: "results.data.x"
"""

import json
import numpy as N

from .. import qtall as qt
from .. import document
from .. import datasets
from . import base

def _(text, disambiguation=None, context="Import_JSON"):
    return qt.QCoreApplication.translate(context, text, disambiguation)

class ImportParamsJSON(base.ImportParamsBase):
    """JSON import parameters.

    additional parameters:
     rootpath: dot-separated path to data root (e.g. 'results.data')
    """

    defaults = {
        'rootpath': '',
    }
    defaults.update(base.ImportParamsBase.defaults)

class OperationDataImportJSON(base.OperationDataImportBase):
    """Import data from a JSON file."""

    descr = _('import JSON data')

    def doImport(self):
        """Do the data import."""
        p = self.params

        try:
            with open(p.filename, 'r', encoding=p.encoding) as f:
                rawdata = json.load(f)
        except FileNotFoundError:
            raise base.ImportingError(
                _("File not found: %s") % p.filename)
        except json.JSONDecodeError as e:
            raise base.ImportingError(
                _("Invalid JSON in %s: %s") % (p.filename, str(e)))
        except Exception as e:
            raise base.ImportingError(
                _("Error reading %s: %s") % (p.filename, str(e)))

        # navigate to root path
        data = rawdata
        if p.rootpath:
            for key in p.rootpath.split('.'):
                key = key.strip()
                if key:
                    if isinstance(data, dict):
                        if key not in data:
                            raise base.ImportingError(
                                _("Key '%s' not found in JSON") % key)
                        data = data[key]
                    elif isinstance(data, list):
                        try:
                            data = data[int(key)]
                        except (ValueError, IndexError):
                            raise base.ImportingError(
                                _("Invalid index '%s' in JSON array") % key)
                    else:
                        raise base.ImportingError(
                            _("Cannot navigate into '%s'") % key)

        LF = None
        if p.linked:
            LF = LinkedFileJSON(p)

        prefix = p.prefix
        suffix = p.suffix

        if isinstance(data, dict):
            # Object of arrays: {"x": [...], "y": [...]}
            self._importDict(data, prefix, suffix, LF)
        elif isinstance(data, list) and len(data) > 0:
            if isinstance(data[0], dict):
                # Array of objects: [{"x":1,"y":2}, ...]
                self._importListOfDicts(data, prefix, suffix, LF)
            else:
                # Plain array of numbers
                name = prefix + 'data' + suffix
                arr = self._toNumpy(data)
                if arr is not None:
                    self.outdatasets[name] = datasets.Dataset(
                        data=arr, linked=LF)
        else:
            raise base.ImportingError(
                _('JSON data must be an object or array'))

    def _toNumpy(self, values):
        """Convert list of values to numpy array, or None if not numeric."""
        try:
            arr = N.array(values, dtype=N.float64)
            return arr
        except (ValueError, TypeError):
            return None

    def _importDict(self, data, prefix, suffix, LF):
        """Import from dict of arrays."""
        for key, values in data.items():
            if isinstance(values, (list, tuple)):
                arr = self._toNumpy(values)
                if arr is not None:
                    name = prefix + str(key) + suffix
                    self.outdatasets[name] = datasets.Dataset(
                        data=arr, linked=LF)
            elif isinstance(values, (int, float)):
                name = prefix + str(key) + suffix
                self.outdatasets[name] = datasets.Dataset(
                    data=N.array([values]), linked=LF)

    def _importListOfDicts(self, data, prefix, suffix, LF):
        """Import from list of objects."""
        # collect all keys
        keys = []
        seen = set()
        for row in data:
            if isinstance(row, dict):
                for k in row:
                    if k not in seen:
                        keys.append(k)
                        seen.add(k)

        # extract columns
        for key in keys:
            values = []
            for row in data:
                if isinstance(row, dict) and key in row:
                    v = row[key]
                    if isinstance(v, (int, float)):
                        values.append(v)
                    else:
                        values.append(N.nan)
                else:
                    values.append(N.nan)

            arr = N.array(values, dtype=N.float64)
            if N.any(N.isfinite(arr)):
                name = prefix + str(key) + suffix
                self.outdatasets[name] = datasets.Dataset(
                    data=arr, linked=LF)

class LinkedFileJSON(base.LinkedFileBase):
    """A JSON file linked to datasets."""

    def createOperation(self):
        return OperationDataImportJSON

    def saveToFile(self, fileobj, relpath=None):
        self._saveHelper(
            fileobj,
            'ImportFileJSON',
            ('filename',),
            renameparams={'prefix': 'dsprefix', 'suffix': 'dssuffix'},
            relpath=relpath)

def ImportFileJSON(comm, filename,
                   rootpath='',
                   encoding='utf_8',
                   dsprefix='', dssuffix='',
                   renames=None,
                   linked=False):
    """Read data from a JSON file.

    JSON format can be:
     - Object of arrays: {"x": [1,2,3], "y": [4,5,6]}
     - Array of objects: [{"x":1,"y":4}, {"x":2,"y":5}]
     - Nested: use rootpath to navigate (e.g. 'results.data')

    rootpath: dot-separated path into JSON structure
    encoding: file encoding
    dsprefix: prefix for dataset names
    dssuffix: suffix for dataset names
    renames: dict mapping old names to new names
    linked: if True, link to the file

    Returns: list of imported dataset names
    """
    realfilename = comm.findFileOnImportPath(filename)
    params = ImportParamsJSON(
        filename=realfilename,
        rootpath=rootpath,
        encoding=encoding,
        prefix=dsprefix,
        suffix=dssuffix,
        renames=renames,
        linked=linked,
    )
    op = OperationDataImportJSON(params)
    comm.document.applyOperation(op)

    if comm.verbose:
        print("Imported datasets %s" % ' '.join(op.outnames))
    return op.outnames

document.registerImportCommand('ImportFileJSON', ImportFileJSON)

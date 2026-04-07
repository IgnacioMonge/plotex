#    Copyright (C) 2011 Jeremy S. Sanders
#    Email: Jeremy Sanders <jeremy@jeremysanders.net>
#
#    This file is part of Veusz.
#
#    Veusz is free software: you can redistribute it and/or modify it
#    under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 2 of the License, or
#    (at your option) any later version.
#
#    Veusz is distributed in the hope that it will be useful, but
#    WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#    General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Veusz. If not, see <https://www.gnu.org/licenses/>.
#
##############################################################################

"""Parameters for import routines."""

import sys
import copy

import numpy as N

from .. import utils
from .. import datasets

class ImportingError(RuntimeError):
    """Common error when import fails."""

class ImportParamsBase:
    """Import parameters for the various imports.

    Parameters:
     filename: filename to import from
     linked: whether to link to file
     encoding: encoding for file
     prefix: prefix for output dataset names
     suffix: suffix for output dataset names
     tags: list of tags to apply to output datasets
     renames: dict map of names to renamed datasets
    """

    defaults = {
        'filename': None,
        'linked': False,
        'encoding': 'utf_8',
        'prefix': '',
        'suffix': '',
        'tags': None,
        'renames': None,
    }

    def __init__(self, **argsv):
        """Initialise the reader to import data from filename.
        """

        #  set defaults
        for k, v in self.defaults.items():
            setattr(self, k, v)

        # set parameters
        for k, v in argsv.items():
            if k not in self.defaults:
                raise ValueError("Invalid parameter %s" % k)
            setattr(self, k, v)

        # extra parameters to copy besides defaults
        self._extras = []

    def copy(self):
        """Make a copy of the parameters object."""

        newp = {}
        for k in list(self.defaults.keys()) + self._extras:
            newp[k] = getattr(self, k)
        return self.__class__(**newp)

class LinkedFileBase:
    """A base class for linked files containing common routines."""

    def __init__(self, params):
        """Save parameters."""
        self.params = params

    def createOperation(self):
        """Return operation to recreate self."""
        return None

    @property
    def filename(self):
        """Get filename."""
        return self.params.filename

    def _saveHelper(self, fileobj, cmd, fixedparams,
                    renameparams={}, relpath=None, extraargs={}):
        """Helper to write command to reload data.

        fileobj: file object to write to
        cmd: name of command to write
        fixedparams: list of parameters to list at start of command lines
        renameparams: optional map of params to command line params
        relpath: relative path for writing filename
        extraargs: other options to add to command line
        """

        p = self.params
        args = []

        # arguments without names at command start
        for par in fixedparams:
            if par == 'filename':
                v = self._getSaveFilename(relpath)
            else:
                v = getattr(p, par)
            args.append(utils.rrepr(v))

        # parameters key, values to put in command line
        plist = sorted(
            [(par, getattr(p, par)) for par in p.defaults] +
            list(extraargs.items())
        )

        for par, val in plist:
            if ( val and
                 (par not in p.defaults or p.defaults[par] != val) and
                 par not in fixedparams and
                 par != 'tags' ):

                if par in renameparams:
                    par = renameparams[par]
                args.append('%s=%s' % (par, utils.rrepr(val)))

        # write command using comma-separated list
        fileobj.write('%s(%s)\n' % (cmd, ', '.join(args)))

    def saveToFile(self, fileobj, relpath=None):
        """Save the link to the document file."""
        pass

    def _getSaveFilename(self, relpath):
        """Get filename to write to save file.
        If relpath is a string, write relative to path given
        """
        if relpath:
            f = utils.relpath(self.params.filename, relpath)
        else:
            f = self.filename
        # Here we convert backslashes in Windows to forward slashes
        # This is compatible, but also works on Unix/Mac
        if sys.platform == 'win32':
            f = f.replace('\\', '/')
        return f

    def _deleteLinkedDatasets(self, document):
        """Delete linked datasets from document linking to self.
        Returns tags for deleted datasets.
        """

        tags = {}
        for name, ds in list(document.data.items()):
            if ds.linked == self:
                tags[name] = document.data[name].tags
                document._deleteDataUnlocked(name)
        return tags

    def _moveReadDatasets(self, tempdoc, document, tags):
        """Move datasets from tempdoc to document if they do not exist
        in the destination.

        tags is a dict of tags for each dataset
        """

        read = []
        for name, ds in list(tempdoc.data.items()):
            if name not in document.data:
                ds.linked = self
                if name in tags:
                    ds.tags = tags[name]
                document._setDataUnlocked(name, ds)
                read.append(name)
        return read

    def reloadLinks(self, document):
        """Reload links using an operation"""

        # get the operation for reloading
        op = self.createOperation()(self.params)

        # load data into a temporary document
        tempdoc = document.__class__()

        try:
            tempdoc.applyOperation(op)
        except Exception as ex:
            # if something breaks, record an error and return nothing
            document.log(str(ex))

            # find datasets which are linked using this link object
            # return errors for them
            errors = dict(
                [(name, 1) for name, ds in document.data.items()
                 if ds.linked is self])
            return ([], errors)

        # delete datasets which are linked and imported here
        tags = self._deleteLinkedDatasets(document)
        # move datasets into document
        read = self._moveReadDatasets(tempdoc, document, tags)

        # return errors (if any)
        errors = op.outinvalids

        return (read, errors)

class OperationDataImportBase:
    """Default useful import class."""

    def __init__(self, params):
        self.params = params

    def doImport(self, document):
        """Do import, override this.
        Set outdatasets
        """

    def addCustoms(self, document, customs):
        """Optionally, add the customs return by plugins to document."""

        type_attrs = {
            'import': 'def_imports',
            'color': 'def_colors',
            'colormap': 'def_colormaps',
            'constant': 'def_definitions',
            'function': 'def_definitions',
            'definition': 'def_definitions',
        }

        if len(customs) > 0:
            doceval = document.evaluate
            self.oldcustoms = [
                copy.deepcopy(doceval.def_imports),
                copy.deepcopy(doceval.def_definitions),
                copy.deepcopy(doceval.def_colors),
                copy.deepcopy(doceval.def_colormaps)]

            # FIXME: inefficient for large number of definitions
            for item in customs:
                ctype, name, val = item
                clist = getattr(doceval, type_attrs[ctype])
                for idx, (cname, cval) in enumerate(clist):
                    if cname == name:
                        clist[idx][1] = val
                        break
                else:
                    clist.append([name, val])

            doceval.update()

    def preloadImport(self):
        """Run doImport() to read data without touching the document.

        After calling this, do() will skip the I/O phase and just
        apply the pre-loaded datasets to the document.  This allows
        the heavy file I/O to run in a background thread.
        """
        self.outnames = []
        self.outdatasets = {}
        self.outcustoms = []
        self.outinvalids = {}
        self.oldcustoms = None
        self.doImport()
        self._preloaded = True

    def do(self, document):
        """Do import."""

        if not getattr(self, '_preloaded', False):
            # list of returned dataset names
            self.outnames = []
            # map of names to datasets
            self.outdatasets = {}
            # list of returned custom variables
            self.outcustoms = []
            # invalid conversions
            self.outinvalids = {}

            # remember datasets in document for undo
            self.oldcustoms = None

            # do actual import
            retn = self.doImport()
        else:
            retn = None

        # these are custom values returned from the plugin
        if self.outcustoms:
            self.addCustoms(document, self.outcustoms)

        # handle tagging/renaming
        for name, ds in list(self.outdatasets.items()):
            if self.params.tags:
                ds.tags.update(self.params.tags)
            if self.params.renames and name in self.params.renames:
                del self.outdatasets[name]
                self.outdatasets[self.params.renames[name]] = ds

        # only remember the parts we need
        self.olddatasets = [
            (n, document.data.get(n)) for n in self.outdatasets ]

        self.olddatasets = []
        for name, ds in self.outdatasets.items():
            self.olddatasets.append( (name, document.data.get(name)) )
            document._setDataUnlocked(name, ds)

        self.outnames = sorted(self.outdatasets)

        return retn

    def undo(self, document):
        """Undo import."""

        # put back old datasets
        for name, ds in self.olddatasets:
            if ds is None:
                document._deleteDataUnlocked(name)
            else:
                document._setDataUnlocked(name, ds)

        # for custom definitions
        if self.oldcustoms is not None:
            doceval = document.evaluate
            doceval.def_imports = self.oldcustoms[0]
            doceval.def_definitions = self.oldcustoms[1]
            doceval.def_colors = self.oldcustoms[2]
            doceval.def_colormaps = self.oldcustoms[3]
            doceval.update()


def rows_to_datasets(allrows, headerrow, prefix, suffix, linkedfile):
    """Convert tabular rows into Dataset/DatasetText objects.

    Common helper for Excel and ODS importers.

    Returns dict of {fullname: dataset}.
    """
    if not allrows:
        return {}

    ncols = max(len(r) for r in allrows) if allrows else 0

    # extract headers
    if headerrow and len(allrows) > 0:
        headers = []
        for i in range(ncols):
            val = allrows[0][i] if i < len(allrows[0]) else None
            headers.append(str(val) if val is not None else 'col%d' % (i+1))
        datarows = allrows[1:]
    else:
        headers = ['col%d' % (i+1) for i in range(ncols)]
        datarows = allrows

    if not datarows:
        return {}

    outdatasets = {}
    for col_idx in range(ncols):
        name = headers[col_idx].strip()
        if not name:
            name = 'col%d' % (col_idx + 1)

        # quick check: skip columns where every cell is empty/None
        has_data = False
        for row in datarows:
            v = row[col_idx] if col_idx < len(row) else None
            if v is not None and v != '':
                has_data = True
                break
        if not has_data:
            continue

        # collect column values, trying to coerce strings to numbers
        vals = []
        is_numeric = True
        for row in datarows:
            v = row[col_idx] if col_idx < len(row) else None
            if v is None or v == '':
                vals.append(N.nan if is_numeric else v)
            elif isinstance(v, (int, float)):
                vals.append(float(v))
            elif isinstance(v, str):
                try:
                    vals.append(float(v.replace(',', '.')))
                except (ValueError, AttributeError):
                    is_numeric = False
                    vals.append(v)
            else:
                is_numeric = False
                vals.append(v)

        # backfill None/empty as text if column turned out non-numeric
        if not is_numeric:
            vals = [
                (str(v) if v is not None and v == v else '')
                for v in vals
            ]

        if is_numeric:
            ds = datasets.Dataset(data=N.array(vals, dtype=N.float64))
        else:
            textvals = []
            for v in vals:
                if v is None or (isinstance(v, float) and N.isnan(v)):
                    textvals.append('')
                else:
                    textvals.append(str(v))
            ds = datasets.DatasetText(data=textvals)

        ds.linked = linkedfile
        fullname = prefix + name + suffix
        outdatasets[fullname] = ds

    return outdatasets

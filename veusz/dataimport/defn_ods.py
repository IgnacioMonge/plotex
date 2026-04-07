#    Copyright (C) 2026 M. Ignacio Monge Garcia
#
#    This file is part of Plotex (based on Veusz).
#
##############################################################################

"""OpenDocument Spreadsheet (.ods) data import definitions."""

from .. import qtall as qt
from .. import document
from .. import utils
from . import base

def _(text, disambiguation=None, context='Import'):
    return qt.QCoreApplication.translate(context, text, disambiguation)


def _read_ods_file(filename, sheet_name=''):
    """Read an ODS file and return (sheet_names, rows_of_selected_sheet).

    Parses the file only ONCE.  If *sheet_name* is given and found, its
    data is returned; otherwise the first sheet is used.

    Each row is a list of cell values (str, float, or None).
    """
    from odf.opendocument import load
    from odf import table as odftable
    from odf import text as odftext

    doc = load(filename)
    sheets = doc.spreadsheet.getElementsByType(odftable.Table)
    sheet_names = [s.getAttribute('name') for s in sheets]

    if not sheets:
        return sheet_names, []

    # pick sheet by name, fall back to first
    idx = 0
    if sheet_name and sheet_name in sheet_names:
        idx = sheet_names.index(sheet_name)
    ws = sheets[idx]

    rows = []
    for tr in ws.getElementsByType(odftable.TableRow):
        row = []
        for tc in tr.getElementsByType(odftable.TableCell):
            repeat = tc.getAttribute('numbercolumnsrepeated')
            repeat = int(repeat) if repeat else 1
            # limit repeats to avoid huge empty rows
            repeat = min(repeat, 1000)

            # get cell value
            val_type = tc.getAttribute('valuetype')
            if val_type == 'float':
                val = tc.getAttribute('value')
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    val = None
            elif val_type == 'string' or val_type == 'date':
                # extract text content
                texts = tc.getElementsByType(odftext.P)
                val = ''.join(
                    t.firstChild.data if t.firstChild else ''
                    for t in texts)
                if not val:
                    val = None
            else:
                val = None

            for _ in range(repeat):
                row.append(val)

        # trim trailing None cells in this row
        while row and row[-1] is None:
            row.pop()
        if row:
            rows.append(row)

    # trim trailing empty rows
    while rows and all(v is None for v in rows[-1]):
        rows.pop()

    return sheet_names, rows


class ImportParamsODS(base.ImportParamsBase):
    """Parameters for ODS import."""

    defaults = {
        'sheet': '',
        'headerrow': True,
        'skiprows': 0,
    }
    defaults.update(base.ImportParamsBase.defaults)


class OperationDataImportODS(base.OperationDataImportBase):
    """Operation to import data from an ODS file."""

    descr = _('import ODS data')

    def doImport(self):
        p = self.params

        try:
            sheet_names, allrows = _read_ods_file(p.filename, p.sheet)
        except base.ImportingError:
            raise
        except Exception as e:
            raise base.ImportingError(
                _('Error opening ODS file: %s') % str(e))

        if not allrows:
            return

        # skip rows
        if p.skiprows > 0:
            allrows = allrows[p.skiprows:]
        if not allrows:
            return

        LF = LinkedFileODS(p) if p.linked else None
        self.outdatasets = base.rows_to_datasets(
            allrows, p.headerrow, p.prefix, p.suffix, LF)


class LinkedFileODS(base.LinkedFileBase):
    """Represents a linked ODS file."""

    def createOperation(self):
        return OperationDataImportODS

    def saveToFile(self, fileobj, relpath=None):
        self._saveHelper(
            fileobj,
            'ImportFileODS',
            ('filename',),
            renameparams={'prefix': 'dsprefix', 'suffix': 'dssuffix'},
            relpath=relpath)


def ImportFileODS(comm, filename, sheet='', headerrow=True,
                  skiprows=0, dsprefix='', dssuffix='',
                  renames=None, linked=False, encoding='utf_8'):
    """Import data from an ODS (.ods) file."""

    realfilename = comm.findFileOnImportPath(filename)
    params = ImportParamsODS(
        filename=realfilename,
        sheet=sheet,
        headerrow=headerrow,
        skiprows=skiprows,
        prefix=dsprefix,
        suffix=dssuffix,
        renames=renames,
        linked=linked,
        encoding=encoding,
    )
    op = OperationDataImportODS(params)
    comm.document.applyOperation(op)
    if comm.verbose:
        print("Imported datasets: %s" % ', '.join(op.outnames))
    return op.outnames

document.registerImportCommand('ImportFileODS', ImportFileODS)

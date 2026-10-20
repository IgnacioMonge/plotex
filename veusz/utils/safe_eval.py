#    Copyright (C) 2013 Jeremy S. Sanders
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

"""
'Safe' python code evaluation

The idea is to examine the compiled ast tree and chack for invalid
entries
"""

import ast
import builtins
import numpy as N

from .. import qtall as qt


def _(text, disambiguation=None, context="SafeEval"):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)


# Binding names or creating callable objects requires document trust.
allowed_nodes = (
    ast.Expression, ast.Module, ast.Expr, ast.Call, ast.Name, ast.Constant,
    ast.List, ast.Tuple, ast.Dict, ast.Set, ast.Load, ast.keyword,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Subscript, ast.Slice, ast.Attribute,
    ast.operator, ast.unaryop, ast.boolop, ast.cmpop,
    ast.Index, ast.ExtSlice,
)

# whitelist of allowed builtins
allowed_builtins = frozenset(
    (
        "ArithmeticError",
        "AttributeError",
        "BaseException",
        "Exception",
        "False",
        "FloatingPointError",
        "IndexError",
        "KeyError",
        "NameError",
        "None",
        "OverflowError",
        "RuntimeError",
        "StandardError",
        "StopIteration",
        "True",
        "TypeError",
        "ValueError",
        "ZeroDivisionError",
        "abs",
        "all",
        "any",
        "apply",
        "basestring",
        "bin",
        "bool",
        "bytes",
        "callable",
        "chr",
        "cmp",
        "complex",
        "dict",
        "divmod",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "hash",
        "hex",
        "id",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "long",
        "map",
        "max",
        "min",
        "next",
        "object",
        "oct",
        "ord",
        "pow",
        "print",
        "property",
        "range",
        "reduce",
        "repr",
        "reversed",
        "round",
        "set",
        "slice",
        "sorted",
        "str",
        "sum",
        "tuple",
        "unichr",
        "unicode",
        "xrange",
        "zip",
    )
)

numpy_forbidden = set(
    (
        "frombuffer",
        "fromfile",
        "getbuffer",
        "getbufsize",
        "load",
        "loads",
        "loadtxt",
        "memmap",
        "genfromtxt",
        "fromregex",
        "DataSource",
        "ndfromtxt",
        "newbuffer",
        "pkgload",
        "recfromcsv",
        "recfromtxt",
        "save",
        "savetxt",
        "savez",
        "savez_compressed",
        "setbufsize",
        "seterr",
        "seterrcall",
        "seterrobj",
    )
)

# Array metadata is useful; methods, native pointers and module traversal are not.
allowed_attrs = frozenset(
    ("shape", "ndim", "size", "dtype", "itemsize", "nbytes", "T", "real", "imag")
)

# Deliberately opt in to numerical functions, not every callable NumPy exports.
numpy_safe_names = frozenset("""
array asarray asanyarray copy zeros zeros_like ones ones_like full full_like
arange linspace logspace geomspace eye identity diag diagonal diagflat
reshape ravel transpose swapaxes moveaxis squeeze expand_dims
concatenate stack vstack hstack dstack column_stack row_stack
split array_split hsplit vsplit dsplit repeat tile
where choose select take compress extract nonzero flatnonzero argwhere
sort argsort lexsort searchsorted unique
sum prod cumsum cumprod mean std var median percentile quantile
nanmean nanstd nanvar nanmedian nanpercentile nanquantile nansum nanprod
min max amin amax nanmin nanmax argmin argmax nanargmin nanargmax
all any allclose isclose diff gradient ediff1d
clip round around fix angle real imag real_if_close nan_to_num
dot inner outer tensordot einsum cross
interp histogram histogram2d histogramdd bincount digitize
trapz trapezoid meshgrid indices tril triu fliplr flipud flip rot90
polyval polyfit roots convolve correlate
float16 float32 float64 longdouble int8 int16 int32 int64
uint8 uint16 uint32 uint64 complex64 complex128 bool_
""".split())
numpy_safe_context = {
    name: value for name, value in vars(N).items()
    if not name.startswith("_") and name not in vars(builtins) and (
        isinstance(value, N.ufunc) or type(value) is float or name in numpy_safe_names
    )
}

# blacklist using whitelist above
forbidden_builtins = set(builtins.__dict__.keys()) - allowed_builtins | numpy_forbidden


class SafeEvalException(Exception):
    """Raised by safety errors in code."""

    pass


class CheckNodeVisitor(ast.NodeVisitor):
    """Visit ast nodes to look for unsafe entries."""

    def __init__(self, allowed_calls=()):
        self.allowed_calls = allowed_builtins | numpy_safe_context.keys() | set(allowed_calls)

    def generic_visit(self, node):
        if not isinstance(node, allowed_nodes):
            raise SafeEvalException(_("%s not safe") % type(node))
        ast.NodeVisitor.generic_visit(self, node)

    def visit_Name(self, name):
        if name.id[:2] == "__" or name.id in forbidden_builtins:
            raise SafeEvalException(
                _('Access to special names not allowed: "%s"') % name.id
            )
        self.generic_visit(name)

    def visit_Call(self, call):
        # Only bare-name calls are permitted (e.g. ``sin(x)``). Anything
        # else — ``obj.method(...)``, ``foo[0](...)``, ``(lambda: ...)()``,
        # ``getattr(x, 'y')(...)`` — is rejected at parse time. Attribute
        # access is already restricted by visit_Attribute, but a callee
        # that isn't a Name can hide indirection the AST walker won't see
        # later, so reject up front.
        if not isinstance(call.func, ast.Name):
            raise SafeEvalException(
                _("Only direct calls to whitelisted names are allowed")
            )

        if call.func.id[:2] == "__" or call.func.id in forbidden_builtins:
            raise SafeEvalException(
                _('Access to special functions not allowed: "%s"') % call.func.id
            )
        if call.func.id not in self.allowed_calls:
            raise SafeEvalException(_('Function not allowed: "%s"') % call.func.id)
        self.generic_visit(call)

    def visit_Attribute(self, attr):
        name = attr.attr
        if name not in allowed_attrs:
            raise SafeEvalException(
                _('Access to attribute "%s" not allowed in safe mode') % name
            )
        self.generic_visit(attr)


def compileChecked(code, mode="eval", filename="<string>", ignoresecurity=False,
                   allowed_calls=()):
    """Compile code, checking for security errors.

    Returns a compiled code object.
    mode = 'exec' or 'eval'
    """

    try:
        tree = ast.parse(code, filename, mode)
    except Exception as e:
        raise ValueError(_("Unable to parse file: %s") % str(e))

    if not ignoresecurity:
        visitor = CheckNodeVisitor(allowed_calls)
        visitor.visit(tree)

    compiled = compile(tree, filename, mode)

    return compiled

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

from .. import qtall as qt


def _(text, disambiguation=None, context="SafeEval"):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)


# blacklist of AST node types. The blacklist is intentionally explicit:
# anything that can introduce bindings the visitor can't see (Import*,
# Global), produce callable objects whose identity can't be checked at
# parse time (Lambda, comprehensions), bypass name resolution
# (NamedExpr := walrus, Starred), or smuggle code through formatting
# (JoinedStr / FormattedValue, which invoke __format__ on arbitrary
# objects).
forbidden_nodes = set(
    (
        ast.Global,
        ast.Import,
        ast.ImportFrom,
        ast.Lambda,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
        ast.Starred,
        ast.JoinedStr,
        ast.FormattedValue,
        ast.Yield,
        ast.YieldFrom,
        ast.Await,
    )
)

if hasattr(ast, "NamedExpr"):
    forbidden_nodes.add(ast.NamedExpr)
if hasattr(ast, "Exec"):
    forbidden_nodes.add(ast.Exec)
if hasattr(ast, "AsyncFunctionDef"):
    forbidden_nodes.add(ast.AsyncFunctionDef)

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

# Attribute names that should never be reachable in safe-mode
# expressions — even if the user is dotting through an object whose
# runtime type the AST walker can't determine. The set covers numpy
# submodules that expose I/O, C-interop, or compiler functionality, and
# a few introspection helpers that double as attribute enumerators.
# Anything reaching for ``something.lib.npyio.read_array_header_1_0``
# or ``np.ctypeslib`` or ``np.f2py.compile`` is rejected at parse time.
forbidden_attrs = frozenset(
    (
        "lib",
        "core",
        "distutils",
        "f2py",
        "testing",
        "ctypeslib",
        "tests",
        "system_info",
        "show_config",
        "info",
        "lookfor",
        "source",
        "compile",
        "test",
        "setup",
        # Generic Python attributes that would otherwise smuggle escapes
        "globals",
        "locals",
        "vars",
        "dir",
        "exec",
        "eval",
        "compile",
        "open",
        "input",
        "breakpoint",
        "exit",
        "quit",
        "subclasshook",
    )
)

# blacklist using whitelist above
forbidden_builtins = set(builtins.__dict__.keys()) - allowed_builtins | numpy_forbidden


class SafeEvalException(Exception):
    """Raised by safety errors in code."""

    pass


class CheckNodeVisitor(ast.NodeVisitor):
    """Visit ast nodes to look for unsafe entries."""

    def generic_visit(self, node):
        if type(node) in forbidden_nodes:
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
        self.generic_visit(call)

    def visit_Attribute(self, attr):
        if not hasattr(attr, "attr"):
            raise SafeEvalException(_("Access denied to attribute"))
        name = attr.attr
        if (
            name[:2] == "__"
            or name[:5] == "func_"
            or name[:3] == "im_"
            or name[:3] == "tb_"
        ):
            raise SafeEvalException(
                _('Access to special attributes not allowed: "%s"') % name
            )
        if name in forbidden_attrs:
            raise SafeEvalException(
                _('Access to attribute "%s" not allowed in safe mode') % name
            )
        self.generic_visit(attr)


def compileChecked(code, mode="eval", filename="<string>", ignoresecurity=False):
    """Compile code, checking for security errors.

    Returns a compiled code object.
    mode = 'exec' or 'eval'
    """

    try:
        tree = ast.parse(code, filename, mode)
    except Exception as e:
        raise ValueError(_("Unable to parse file: %s") % str(e))

    if not ignoresecurity:
        visitor = CheckNodeVisitor()
        visitor.visit(tree)

    compiled = compile(tree, filename, mode)

    return compiled

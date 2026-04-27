#    Copyright (C) 2026 Plotex contributors
#
#    This file is part of Plotex (a Veusz fork).
#
#    Veusz is free software: you can redistribute it and/or modify it
#    under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 2 of the License, or
#    (at your option) any later version.

"""QPainter state-stack helpers.

The bare ``painter.save()`` / ``painter.restore()`` pair is fragile: if any
draw call between them raises, ``restore()`` is skipped and the painter's
state stack stays unbalanced for the rest of the page (or the whole batch
export). The fix is to always pair them in a ``try/finally``. This module
provides a context manager that does that without the boilerplate.

Usage::

    from .. import utils

    with utils.painter_state(painter):
        painter.setClipRect(rect)
        painter.setPen(pen)
        painter.drawPath(path)   # may raise; state is still restored

The context manager calls ``save()`` on entry and ``restore()`` on exit,
even when the body raises. It does not swallow exceptions.
"""

from contextlib import contextmanager


def safe_singleShot(ms, widget, callback):
    """Like ``QTimer.singleShot(ms, callback)`` but a no-op if ``widget``
    is destroyed before the timer fires.

    The Qt convenience signature ``singleShot(ms, widget, slot)`` already
    auto-disconnects when ``widget`` is destroyed at the C++ level, but
    only when ``slot`` is a bound slot of ``widget`` itself. Anywhere
    we pass a lambda or a method of a different object (label, status
    bar, etc.), the timer fires after ``deleteLater`` has run on the
    target and we get an AttributeError or a ``RuntimeError: wrapped
    C/C++ object … has been deleted``.

    Wrap the callback in a check that bails when either ``widget`` or
    the C++ side of the slot's owner is gone.
    """
    from .. import qtall as qt

    try:
        from PyQt6 import sip as _sip
    except ImportError:
        _sip = None

    def _fire():
        try:
            if widget is None:
                return
            if _sip is not None and _sip.isdeleted(widget):
                return
        except Exception:
            return
        try:
            callback()
        except RuntimeError:
            # Wrapped C++ object referenced inside the callback was
            # already deleted — silently swallow; the user closed the
            # owning dialog and the cleanup is now meaningless.
            pass

    qt.QTimer.singleShot(ms, _fire)


@contextmanager
def painter_state(painter):
    """Save painter state on enter, restore on exit, even if body raises.

    Equivalent to::

        painter.save()
        try:
            ...
        finally:
            painter.restore()
    """
    painter.save()
    try:
        yield painter
    finally:
        painter.restore()

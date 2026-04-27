"""Shared pytest fixtures for the Plotex test suite.

A single ``QApplication`` is needed before importing any Veusz module,
otherwise widgets and font handling raise. Pre-fix every test module
re-created its own at import time, leaving stray instances and using
``[]`` for argv (which trips some Qt locales). This conftest creates
exactly one for the whole session.
"""

import os
import sys

import pytest

# Headless platform plugin so the suite runs on CI / over SSH without
# an X server. Caller can override by exporting QT_QPA_PLATFORM ahead
# of pytest.
os.environ.setdefault("QT_QPA_PLATFORM", "minimal")


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Process-wide QApplication instance shared by every test."""
    from PyQt6 import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv[:1])
    yield app
    # Don't quit() the app at session end: Qt sometimes segfaults when
    # asked to tear down state owned by static C++ globals from another
    # site-packages module. Letting Python exit handles it.

#    Copyright (C) 2014 Jeremy S. Sanders
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

# note: no future statements here for backward compatibility

import sys
import os.path
import traceback
import io
import re
import numpy as N

from .. import qtall as qt
from .. import utils

from .commandinterface import CommandInterface
from . import datasets

# loaded lazily
h5py = None


def _(text, disambiguation=None, context="DocumentLoader"):
    """Translate text."""
    return qt.QCoreApplication.translate(context, text, disambiguation)


class LoadError(RuntimeError):
    """Error when loading document."""

    def __init__(self, text, backtrace=""):
        RuntimeError.__init__(self, text)
        self.backtrace = backtrace


def bconv(s):
    """Sometimes h5py returns non-unicode strings,
    so hack to decode strings if in wrong format."""
    if isinstance(s, bytes):
        return s.decode("utf-8")
    return s


def _importcaller(interface, name, callbackimporterror):
    """Wrap an import statement to check for IOError."""

    def wrapped(*args, **argsk):
        while True:
            try:
                getattr(interface, name)(*args, **argsk)
            except IOError as e:
                errmsg = str(e)
                fnameidx = interface.import_filenamearg[name]
                assert fnameidx >= 0
                filename = args[fnameidx]
                raiseerror = True
                if callbackimporterror:
                    # used by mainwindow to show dialog and get new filename
                    fname = callbackimporterror(filename, errmsg)
                    if fname is None:
                        # cancel
                        pass
                    elif fname is False:
                        # ignore
                        break
                    else:
                        # put new filename into function argument list
                        args = list(args)
                        args[fnameidx] = fname
                        raiseerror = False
                if raiseerror:
                    # send error message back to UI
                    raise LoadError(
                        _("Error reading file '%s':\n\n%s") % (filename, errmsg)
                    )
            else:
                # imported ok
                break

    return wrapped


import threading


class _LoadBridge(qt.QObject):
    """Bridge object living in the main thread to handle UI callbacks
    requested by the worker thread via blocking signals."""

    sigAskUnsafe = qt.pyqtSignal()
    sigAskImportError = qt.pyqtSignal(str, str)

    def __init__(self, callbackunsafe, callbackimporterror):
        qt.QObject.__init__(self)
        self._callbackunsafe = callbackunsafe
        self._callbackimporterror = callbackimporterror
        self._result = None
        self._event = threading.Event()

    # Hard cap for cross-thread UI callbacks. Without it, a worker can hang
    # forever if the main thread never processes the queued signal (closing
    # window mid-load, GUI suspended by debugger, modal exception elsewhere).
    # 10 minutes is well above any plausible legitimate user reaction time.
    _UI_CALLBACK_TIMEOUT_SEC = 600

    def askUnsafe(self):
        """Called from worker thread. Blocks until main thread responds."""
        self._event.clear()
        self.sigAskUnsafe.emit()
        if not self._event.wait(timeout=self._UI_CALLBACK_TIMEOUT_SEC):
            # Treat timeout as a refusal — never silently grant unsafe exec.
            self._result = False
        return self._result

    def askImportError(self, filename, error):
        """Called from worker thread. Blocks until main thread responds."""
        self._event.clear()
        self.sigAskImportError.emit(filename, error)
        if not self._event.wait(timeout=self._UI_CALLBACK_TIMEOUT_SEC):
            self._result = None
        return self._result

    def _onAskUnsafe(self):
        try:
            if self._callbackunsafe is not None:
                self._result = self._callbackunsafe()
            else:
                self._result = False
        except Exception:
            self._result = False
        finally:
            self._event.set()

    def _onAskImportError(self, filename, error):
        try:
            if self._callbackimporterror is not None:
                self._result = self._callbackimporterror(filename, error)
            else:
                self._result = None
        except Exception:
            self._result = None
        finally:
            self._event.set()


class _FullLoadWorker(qt.QThread):
    """Worker thread that reads and compiles a .vsz script.

    The worker does ONLY file I/O and compilation — no document
    mutation.  Environment construction and exec happen on the
    main thread in applyToDocument().
    """

    sigPhase = qt.pyqtSignal(str)

    def __init__(self, thedoc, filename, bridge):
        qt.QThread.__init__(self)
        self.thedoc = thedoc
        self.filename = filename
        self.bridge = bridge
        self.load_error = None
        self._compiled = None
        self._needs_security = False

    def run(self):
        try:
            # Phase 1: read file
            self.sigPhase.emit(_("Reading file..."))
            try:
                with io.open(self.filename, "r", encoding="utf-8") as f:
                    script = f.read()
            except EnvironmentError as e:
                raise LoadError(
                    _("Cannot open document '%s'\n\n%s")
                    % (os.path.basename(self.filename), e.strerror)
                )
            except UnicodeDecodeError:
                raise LoadError(
                    _("File '%s' is not a valid Veusz document")
                    % os.path.basename(self.filename)
                )
            script = removeBOMs(script)

            # Phase 2: compile only (no document mutation)
            self.sigPhase.emit(_("Compiling document..."))
            self._compiled, self._needs_security = _compileScriptThreaded(
                self.thedoc, self.filename, script, self.bridge
            )
        except LoadError as e:
            self.load_error = e
        except Exception as e:
            info = sys.exc_info()
            backtrace = "".join(traceback.format_exception(*info))
            self.load_error = LoadError(str(e), backtrace=backtrace)

    def applyToDocument(self):
        """Build execution environment and exec on the main thread."""
        if self._compiled is None:
            return
        thedoc = self.thedoc

        # Apply security decision from compile phase (main thread)
        if self._needs_security:
            thedoc.evaluate.setSecurity(True)

        # Build execution environment (main thread — safe)
        from ..dataimport import ensureAllImportersLoaded

        ensureAllImportersLoaded()

        env = thedoc.evaluate.context.copy()
        interface = CommandInterface(thedoc)
        for cmd in interface.safe_commands:
            env[cmd] = getattr(interface, cmd)
        env["Root"] = interface.Root

        bridge = self.bridge

        def _unsafecaller(func):
            def wrapped(*args, **argsk):
                if not thedoc.evaluate.inSecureMode():
                    if not bridge.askUnsafe():
                        raise LoadError(_("Unsafe command in script"))
                    thedoc.evaluate.setSecurity(True)
                func(*args, **argsk)

            return wrapped

        for name in interface.unsafe_commands:
            env[name] = _unsafecaller(getattr(interface, name))

        for name in interface.import_commands:
            env[name] = _importcaller(interface, name, bridge.askImportError)

        env["__file__"] = self.filename
        interface.AddImportPath(os.path.dirname(os.path.abspath(self.filename)))

        # Execute compiled script
        thedoc.loading = True
        ok = False
        try:
            with thedoc.suspend():
                exec(self._compiled, env)
            ok = True
        except Exception as e:
            info = sys.exc_info()
            backtrace = "".join(traceback.format_exception(*info))
            raise LoadError(str(e), backtrace=backtrace)
        finally:
            thedoc.loading = False
            if ok:
                thedoc.changeset += 1
                thedoc.clearHistory()


def _cacheDir():
    """Return the per-user bytecode cache directory, creating it if needed."""
    if sys.platform == "win32":
        base = os.environ.get(
            "LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local")
        )
        cache_dir = os.path.join(base, "Plotex", "cache")
    else:
        base = os.environ.get(
            "XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache")
        )
        cache_dir = os.path.join(base, "plotex")

    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _cachePath(filename):
    """Return the path for the bytecode cache of *filename*.

    Always uses the per-user cache directory returned by ``_cacheDir()``.
    Writing next to the .vsz file (``filename + 'c'``) is avoided because
    ``tempfile.mkstemp`` blocks indefinitely on Windows when the directory
    is protected (e.g. ``C:\\Program Files``), and ``os.access(W_OK)``
    cannot reliably detect this on Windows.
    """
    import hashlib

    path_hash = hashlib.md5(os.path.abspath(filename).encode("utf-8")).hexdigest()
    return os.path.join(_cacheDir(), os.path.basename(filename) + "." + path_hash + "c")


_HMAC_KEY = None  # process-wide cached cache-signing key


def _cacheHmacKey():
    """Return the HMAC-SHA256 key used to sign bytecode cache files.

    The key lives in ``<cache_dir>/.cache_key`` (32 random bytes, chmod 600
    on Unix). It is created lazily on first call and cached for the life of
    the process. If the file is missing, unreadable, or the wrong size, a
    fresh key is generated — which silently invalidates every existing cache
    file (they fail HMAC verification and get recompiled). That trade-off is
    acceptable: cache regeneration is cheap; cache poisoning is not.

    The key authenticates the cache; it does not protect secrecy. Treating
    it like an SSH host key is the right mental model.
    """
    global _HMAC_KEY
    if _HMAC_KEY is not None:
        return _HMAC_KEY

    import secrets

    key_path = os.path.join(_cacheDir(), ".cache_key")
    try:
        with open(key_path, "rb") as f:
            key = f.read()
        if len(key) != 32:
            raise ValueError("cache key wrong size")
    except (OSError, ValueError):
        key = secrets.token_bytes(32)
        try:
            # Atomic write so a partial key never poisons future loads.
            import tempfile

            fd, tmp = tempfile.mkstemp(prefix=".cache_key-", dir=_cacheDir())
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(key)
                if hasattr(os, "chmod"):
                    try:
                        os.chmod(tmp, 0o600)
                    except OSError:
                        pass
                os.replace(tmp, key_path)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except Exception:
            # If we cannot persist the key, fall back to a per-process key.
            # Caches will be invalidated on every restart but never forged.
            pass

    _HMAC_KEY = key
    return key


def _compileScriptThreaded(thedoc, filename, script, bridge):
    """Compile script in worker thread (read-only w.r.t. document).

    Returns (compiled, needs_security) — the execution environment
    is built on the main thread in applyToDocument().
    """

    import hmac
    import marshal

    script_bytes = script.encode("utf-8")
    cachefile = _cachePath(filename)
    compiled = None

    # Try loading cached bytecode. Authenticated with HMAC-SHA256 so an
    # attacker with write access to the cache directory cannot forge a
    # bytecode file that matches the recorded hash — the previous design
    # stored an MD5 of the script *inside* the cache file, which is only a
    # staleness check, not authenticity. Reject symlinks and overly
    # permissive files first; HMAC compare runs in constant time.
    try:
        if (
            os.path.exists(cachefile)
            and not os.path.islink(cachefile)
            and os.path.getmtime(cachefile) >= os.path.getmtime(filename)
        ):
            if hasattr(os, "getuid"):
                st = os.stat(cachefile)
                if st.st_uid != os.getuid():
                    raise ValueError("cache owner mismatch")
                if (st.st_mode & 0o022) != 0:
                    raise ValueError("cache permissions too open")
            with open(cachefile, "rb") as cf:
                stored_mac = cf.read(32)
                marshal_bytes = cf.read()
            if len(stored_mac) == 32 and marshal_bytes:
                expected_mac = hmac.new(
                    _cacheHmacKey(),
                    msg=script_bytes + marshal_bytes,
                    digestmod="sha256",
                ).digest()
                if hmac.compare_digest(stored_mac, expected_mac):
                    compiled = marshal.loads(marshal_bytes)
    except Exception:
        compiled = None

    needs_security = False
    if compiled is None:
        while True:
            try:
                compiled = utils.compileChecked(
                    script,
                    mode="exec",
                    filename=filename,
                    ignoresecurity=(thedoc.evaluate.inSecureMode() or needs_security),
                )
                break
            except utils.SafeEvalException:
                if not bridge.askUnsafe():
                    raise LoadError(_("Unsafe command in script"))
                needs_security = True
            except Exception as e:
                info = sys.exc_info()
                backtrace = "".join(traceback.format_exception(*info))
                raise LoadError(str(e), backtrace=backtrace)

        # save bytecode cache (atomic write with restricted permissions).
        # If we cannot persist the cache, we log a warning instead of
        # silently swallowing the exception: a recurring write failure
        # (full disk, permissions, AV interference) is worth surfacing
        # since every load then takes the slow path.
        try:
            import tempfile

            marshal_bytes = marshal.dumps(compiled)
            mac = hmac.new(
                _cacheHmacKey(),
                msg=script_bytes + marshal_bytes,
                digestmod="sha256",
            ).digest()
            cache_dir = os.path.dirname(os.path.abspath(cachefile))
            fd, tmpname = tempfile.mkstemp(prefix=".vszc-", dir=cache_dir)
            try:
                with os.fdopen(fd, "wb") as cf:
                    cf.write(mac)
                    cf.write(marshal_bytes)
                os.replace(tmpname, cachefile)
            except Exception:
                # leftover tmp: try to remove, ignore unlink errors
                try:
                    if os.path.exists(tmpname):
                        os.unlink(tmpname)
                except OSError:
                    pass
        except Exception as e:
            # Non-critical for correctness — every subsequent load just
            # takes the slow recompile path — but worth surfacing once
            # so the user notices when the cache is permanently broken
            # (read-only profile dir, AV quarantining .vszc, full disk).
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "Plotex bytecode cache write failed for %s: %s", cachefile, e
            )

    return compiled, needs_security


def executeScript(
    thedoc,
    filename,
    script,
    callbackunsafe=None,
    callbackimporterror=None,
    callbackprogress=None,
):
    """Execute a script for the document.

    This handles setting up the environment and checking for unsafe
    commands in the execution.

    filename: filename to supply in __filename__
    script: text to execute
    callbackunsafe: should be set to a function to ask the user whether it is
      ok to execute any unsafe commands found. Return True if ok.
    callbackimporterror(filename, error): should be set to function to return new filename in case of import error, or False if none

    User should wipe docment before calling this.
    """

    def genexception(exc):
        info = sys.exc_info()
        backtrace = "".join(traceback.format_exception(*info))
        return LoadError(str(exc), backtrace=backtrace)

    # compile script and check for security (if reqd)
    while True:
        try:
            compiled = utils.compileChecked(
                script,
                mode="exec",
                filename=filename,
                ignoresecurity=thedoc.evaluate.inSecureMode(),
            )
            break
        except utils.SafeEvalException:
            if callbackunsafe is None or not callbackunsafe():
                raise LoadError(_("Unsafe command in script"))
            # repeat with unsafe mode switched on
            thedoc.evaluate.setSecurity(True)
        except Exception as e:
            raise genexception(e)

    env = thedoc.evaluate.context.copy()
    interface = CommandInterface(thedoc)

    # allow safe commands as-is
    for cmd in interface.safe_commands:
        env[cmd] = getattr(interface, cmd)

    # define root node
    env["Root"] = interface.Root

    # wrap unsafe calls with a function to check whether ok
    def _unsafecaller(func):
        def wrapped(*args, **argsk):
            if not thedoc.evaluate.inSecureMode():
                if callbackunsafe is None or not callbackunsafe():
                    raise LoadError(_("Unsafe command in script"))
                thedoc.evaluate.setSecurity(True)
            func(*args, **argsk)

        return wrapped

    for name in interface.unsafe_commands:
        env[name] = _unsafecaller(getattr(interface, name))

    # override import commands with wrapper
    for name in interface.import_commands:
        env[name] = _importcaller(interface, name, callbackimporterror)

    # get ready for loading document
    env["__file__"] = filename
    # allow import to happen relative to loaded file
    interface.AddImportPath(os.path.dirname(os.path.abspath(filename)))

    with thedoc.suspend():
        try:
            exec(compiled, env)
        except LoadError:
            raise
        except Exception as e:
            raise genexception(e)


def loadHDF5Dataset1D(datagrp):
    args = {}
    # this weird usage of sets is to work around some sort of weird
    # error where h5py gives an error when doing 'a' in datagrp
    # this gives error: 'perr' in datagrp
    parts = set(datagrp) & set(("data", "serr", "perr", "nerr"))
    for v in parts:
        args[v] = N.array(datagrp[v])
    return datasets.Dataset(**args)


def loadHDF5Dataset2D(datagrp):
    args = {}
    parts = set(datagrp) & set(
        ("data", "xcent", "xedge", "ycent", "yedge", "xrange", "yrange")
    )
    for v in parts:
        args[v] = N.array(datagrp[v])
    return datasets.Dataset2D(**args)


def loadHDF5DatasetDate(datagrp):
    return datasets.DatasetDateTime(data=datagrp["data"])


def loadHDF5DatasetText(datagrp):
    data = [d.decode("utf-8") for d in datagrp["data"]]
    return datasets.DatasetText(data=data)


def loadHDF5Datasets(thedoc, hdffile):
    """Load all the Veusz datasets in the HDF5 file."""
    alldatagrp = hdffile["Veusz"]["Data"]

    datafuncs = {
        "1d": loadHDF5Dataset1D,
        "2d": loadHDF5Dataset2D,
        "date": loadHDF5DatasetDate,
        "text": loadHDF5DatasetText,
    }

    for name in alldatagrp:
        datagrp = alldatagrp[name]
        datatype = bconv(datagrp.attrs["vsz_datatype"])
        veuszname = utils.unescapeHDFDataName(bconv(name))

        dataset = datafuncs[datatype](datagrp)
        thedoc._setDataUnlocked(veuszname, dataset)


def tagHDF5Datasets(thedoc, hdffile):
    """Tag datasets loaded from HDF5 file."""
    tags = hdffile["Veusz"]["Document"]["Tags"]
    for tag in tags:
        vsztag = bconv(tag)
        datasets = tags[tag]
        for name in datasets:
            dsname = name.decode("utf-8")
            thedoc.data[dsname].tags.add(vsztag)


def loadHDF5Doc(thedoc, filename, callbackunsafe=None, callbackimporterror=None):
    """Load an HDF5 of the name given."""

    try:
        global h5py
        import h5py
    except ImportError:
        raise LoadError(_("No HDF5 support as h5py module is missing"))

    with thedoc.suspend():
        thedoc.wipe()
        thedoc.filename = filename
        thedoc.evaluate.updateSecurityFromPath()

        with h5py.File(filename, "r") as hdffile:
            try:
                vszformat = hdffile["Veusz"].attrs["vsz_format"]
                vszversion = hdffile["Veusz"].attrs["vsz_version"]
            except KeyError:
                raise LoadError(
                    _("HDF5 file '%s' is not a Veusz saved document")
                    % os.path.basename(filename)
                )

            maxformat = 1
            if vszformat > maxformat:
                raise LoadError(
                    _(
                        "This document version (%i) is not supported. "
                        "It was written by Veusz %s.\n"
                        "This Veusz only supports document version %i."
                    )
                    % (vszformat, vszversion, maxformat)
                )

            # load document
            script = hdffile["Veusz"]["Document"]["document"][0].decode("utf-8")

            # Remove embedded BOM characters
            script = removeBOMs(script)

            executeScript(
                thedoc,
                filename,
                script,
                callbackunsafe=callbackunsafe,
                callbackimporterror=callbackimporterror,
            )

            # then load datasets
            loadHDF5Datasets(thedoc, hdffile)
            # and then tag
            tagHDF5Datasets(thedoc, hdffile)


def _takeDocumentSnapshot(thedoc):
    """Return a side-effect-free snapshot of current document state.

    Holds the document's read lock for the entire snapshot so that the
    serialised script, data dict and history lists are mutually
    consistent. Without this, a render thread (which only takes the read
    lock) or a concurrent operation could mutate ``thedoc.data`` between
    ``serializeToText`` and ``dict(thedoc.data)`` and produce a snapshot
    whose script no longer matches its data — silently corrupting the
    rollback path. ``QReadLocker`` releases the lock even if
    ``serializeToText`` raises.
    """
    render_lock = getattr(thedoc, "_render_lock", None)
    if render_lock is not None:
        locker = qt.QReadLocker(render_lock)
        try:
            return _takeDocumentSnapshotUnlocked(thedoc)
        finally:
            del locker
    return _takeDocumentSnapshotUnlocked(thedoc)


def _takeDocumentSnapshotUnlocked(thedoc):
    snapshot = io.StringIO()
    try:
        thedoc.serializeToText(snapshot)
    except Exception:
        snapshot = None

    return {
        "script": snapshot,
        "data": dict(thedoc.data),
        "filename": thedoc.filename,
        "modified": thedoc.isModified(),
        "changeset": thedoc.changeset,
        "historyundo": list(thedoc.historyundo),
        "historyredo": list(thedoc.historyredo),
    }


def _restoreDocumentSnapshot(
    thedoc, snapshot, load_err, callbackunsafe=None, callbackimporterror=None
):
    """Restore document state after a failed load."""
    thedoc.wipe()
    thedoc.filename = snapshot["filename"]

    if snapshot["script"] is not None:
        try:
            snapshot["script"].seek(0)
            executeScript(
                thedoc,
                snapshot["filename"],
                snapshot["script"].read(),
                callbackunsafe=callbackunsafe,
                callbackimporterror=callbackimporterror,
            )
        except Exception as restore_err:
            raise LoadError(
                _(
                    "Load failed AND rollback failed.\n\n"
                    "Load error: %s\n"
                    "Restore error: %s"
                )
                % (load_err, restore_err),
                backtrace=getattr(load_err, "backtrace", ""),
            )

    thedoc.data = {}
    for name, dataset in snapshot["data"].items():
        thedoc._setDataUnlocked(name, dataset)

    thedoc.historyundo = snapshot["historyundo"]
    thedoc.historyredo = snapshot["historyredo"]
    # setModified() bumps changeset, so restore the saved counter last.
    thedoc.setModified(snapshot["modified"])
    thedoc.changeset = snapshot["changeset"]


def loadDocument(
    thedoc,
    filename,
    mode="vsz",
    callbackunsafe=None,
    callbackimporterror=None,
    callbackprogress=None,
):
    """Load document from file.

    mode is 'vsz' or 'hdf5'
    """

    snapshot = _takeDocumentSnapshot(thedoc)

    try:
        if mode == "vsz":
            # prepare document before worker starts
            thedoc.wipe()
            thedoc.filename = filename
            thedoc.evaluate.updateSecurityFromPath()

            # set up bridge for UI callbacks from worker thread
            bridge = _LoadBridge(callbackunsafe, callbackimporterror)
            bridge.sigAskUnsafe.connect(bridge._onAskUnsafe)
            bridge.sigAskImportError.connect(bridge._onAskImportError)

            # worker reads + compiles in background thread
            worker = _FullLoadWorker(thedoc, filename, bridge)

            def _onPhase(msg):
                if callbackprogress is not None:
                    callbackprogress(-1, 0, msg)

            worker.sigPhase.connect(
                _onPhase, type=qt.Qt.ConnectionType.QueuedConnection
            )

            # local event loop keeps UI alive while worker runs.
            # finished.connect() must happen *before* start(), and we must not
            # enter the loop if the worker already finished — otherwise loop.quit
            # was emitted before loop.exec() and the loop hangs forever.
            loop = qt.QEventLoop()
            worker.finished.connect(loop.quit)
            worker.start()
            if not worker.isFinished():
                loop.exec()

            if worker.load_error is not None:
                raise worker.load_error

            # Phase 3: execute compiled script on main thread
            if callbackprogress is not None:
                callbackprogress(-1, 0, _("Building document..."))
            worker.applyToDocument()
        elif mode == "hdf5":
            loadHDF5Doc(
                thedoc,
                filename,
                callbackunsafe=callbackunsafe,
                callbackimporterror=callbackimporterror,
            )
        else:
            raise RuntimeError("Invalid load mode")
    except LoadError as load_err:
        _restoreDocumentSnapshot(
            thedoc,
            snapshot,
            load_err,
            callbackunsafe=callbackunsafe,
            callbackimporterror=callbackimporterror,
        )
        raise

    thedoc.setModified(False)
    thedoc.clearHistory()


def removeBOMs(script):
    """
    Remove BOMs in the script unless they are escaped.
    For example:
        "AA\ufeffAA" -> "AAAA"
        'C:\\ufeff\\a.csv' -> 'C:\\ufeff\\a.csv'
    """
    pattern = r"(.*?)(\\+)ufeff(.*?)"

    def replacer(m):
        bs = m.group(2)
        if len(bs) % 2 == 0:
            return m.group(0)
        else:
            return f"{m.group(1)}{bs[1:]}{m.group(3)}"

    return re.sub(pattern, replacer, script)

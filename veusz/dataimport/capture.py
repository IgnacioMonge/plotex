#    Copyright (C) 2009 Jeremy S. Sanders
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

import select
import shlex
import subprocess
import os
import socket
import platform
import signal
import threading

from .. import qtall as qt
from .. import utils
from . import simpleread

# Hard cap on the buffered, unflushed bytes of any single capture stream.
# A producer that never emits a newline could otherwise grow self.buffer
# without bound and exhaust memory. 16 MiB is well above any plausible
# single-line measurement payload.
_MAX_BUFFER_BYTES = 16 * 1024 * 1024


def _(text, disambiguation=None, context="Capture"):
    return qt.QCoreApplication.translate(context, text, disambiguation)


class CaptureFinishException(Exception):
    """An exception to say when a stream has been finished."""


class CaptureStream(simpleread.Stream):
    """A special stream for capturing data."""

    def __init__(self):
        """Initialise the stream."""

        simpleread.Stream.__init__(self)
        self.buffer = ""
        self.continuousreads = 0
        self.bytesread = 0
        self.linesread = 0
        self.maxlines = None
        self.timedout = False

    def _setTimeout(self, timeout):
        """Setter for setting timeout property."""
        if timeout:
            # ``QTimer.singleShot`` is a static method that returns
            # ``None``, so ``self.timer = ...`` was assigning None and
            # the attribute name was misleading. Drop the assignment.
            qt.QTimer.singleShot(timeout * 1000, self._timedOut)

    timeout = property(
        None, _setTimeout, None, "Time interval to stop in (seconds) or None"
    )

    def _timedOut(self):
        self.timedout = True

    def getMoreData(self):
        """Override this to return more data from the source without
        blocking."""
        return ""

    def readLine(self):
        """Return a new line of data.

        Either returns new line or
        Raises StopIteration if there is no data, or more than 100 lines
        have been read."""

        while True:
            # we've reached the limit of lines or a timeout has occurred
            if self.linesread == self.maxlines:
                raise CaptureFinishException("Maximum number of lines read")
            if self.timedout:
                raise CaptureFinishException("Maximum time period occurred")

            # stop reading continous data greater than this many lines
            if self.continuousreads == 100:
                self.continuousreads = 0
                raise StopIteration

            index = self.buffer.find("\n")
            if index >= 0:
                # is there a line in the buffer?
                retn = self.buffer[:index]
                self.buffer = self.buffer[index + 1 :]
                self.linesread += 1
                self.continuousreads += 1
                return retn
            else:
                # if not, then read some more data
                data = self.getMoreData()

                if not data:
                    self.continuousreads = 0
                    raise StopIteration
                self.bytesread += len(data)
                self.buffer += data
                if len(self.buffer) > _MAX_BUFFER_BYTES:
                    # Producer is sending unbounded data without newlines.
                    # Stop instead of growing memory until the OS kills us.
                    raise CaptureFinishException(
                        "Capture buffer overflow (>%d bytes without "
                        "newline)" % _MAX_BUFFER_BYTES
                    )

    def close(self):
        """Close any allocated object."""
        pass


class FileCaptureStream(CaptureStream):
    """Capture from a file or named pipe."""

    def __init__(self, filename, encoding="utf-8"):
        CaptureStream.__init__(self)

        # open file; close on failure to avoid fd leak. Pre-fix the
        # encoding was hard-coded to utf-8, so capture from a Latin-1 /
        # cp1252 / shift_jis stream surfaced as decode errors during
        # parse with no way to override.
        self.fileobj = open(filename, "r", encoding=encoding, errors="replace")
        try:
            # make new thread to read file
            self.readerthread = utils.NonBlockingReaderThread(
                self.fileobj, exiteof=False
            )
            self.readerthread.start()
        except Exception:
            self.fileobj.close()
            raise

        self.name = filename

    def getMoreData(self):
        """Read data from the file."""
        try:
            data, done = self.readerthread.getNewData()
            if len(data) == 0 and done:
                raise CaptureFinishException("End of file")
            return data
        except OSError as e:
            raise CaptureFinishException("OSError: %s" % str(e))

    def close(self):
        """Close file."""
        self.fileobj.close()


class CommandCaptureStream(CaptureStream):
    """Capture from an external program."""

    def __init__(self, commandline):
        """Capture from commandline.

        ``commandline`` is parsed with ``shlex.split`` so the child runs
        without an intermediate shell. Quoting still works as expected
        (``'/path with space/cmd' arg1 "arg 2"``) but metacharacters such
        as ``;``, ``|``, ``$()`` and ``&&`` no longer execute extra
        commands. The previous ``shell=True`` form was a shell-injection
        sink whenever the commandline included any user-supplied substring.
        """
        CaptureStream.__init__(self)

        self.name = commandline
        try:
            argv = shlex.split(commandline, posix=(os.name != "nt"))
        except ValueError as e:
            raise CaptureFinishException("Invalid command line: %s" % str(e))
        if not argv:
            raise CaptureFinishException("Empty command line")
        self.popen = subprocess.Popen(
            argv,
            shell=False,
            bufsize=0,
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )

        # make new thread to read stdout
        self.readerthread = utils.NonBlockingReaderThread(self.popen.stdout)
        self.readerthread.start()

    def getMoreData(self):
        """Read data from the command."""

        retn, done = self.readerthread.getNewData()

        if not retn:
            poll = self.popen.poll()
            if poll is not None:
                # process has ended
                raise CaptureFinishException("Process ended (status code %i)" % poll)
        return retn

    def close(self):
        """Close file."""

        if self.popen.poll() is None:
            # Kill child if still running. subprocess.run keeps argv
            # quoted properly and avoids the shell.
            if platform.system() == "Windows":
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(self.popen.pid), "/F"],
                        check=False,
                        timeout=5,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass
            else:
                try:
                    os.kill(self.popen.pid, signal.SIGTERM)
                except OSError:
                    pass

        try:
            self.popen.stdout.close()
        except EnvironmentError:
            # problems closing stdout for some reason
            pass

        # Reap the child so we do not leave a zombie. Bounded wait so we
        # never block the UI thread on a misbehaving process.
        try:
            self.popen.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                self.popen.kill()
                self.popen.wait(timeout=2)
            except Exception:
                pass
        except Exception:
            pass


class SocketCaptureStream(CaptureStream):
    """Capture from an internet host."""

    def __init__(self, host, port):
        """Connect to host and port specified."""
        CaptureStream.__init__(self)

        self.name = "%s:%i" % (host, port)
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))
        except socket.error as e:
            self._handleSocketError(e)

    def _handleSocketError(self, e):
        """Special function to reraise exceptions
        because socket exceptions have changed in python 2.6 and
        behave differently on some platforms.
        """

        # clean up
        self.socket.close()

        # re-raise
        raise e

    def getMoreData(self):
        """Read data from the socket."""

        # see whether there is data to be read
        i, o, e = select.select([self.socket], [], [], 0)
        if i:
            try:
                retn = self.socket.recv(1024)
            except socket.error as e:
                self._handleSocketError(e)
            if len(retn) == 0:
                raise CaptureFinishException("Remote socket closed")
            return retn.decode("utf-8", errors="ignore")
        else:
            return ""

    def close(self):
        """Close the socket."""
        self.socket.close()


class OperationDataCaptureSet:
    """An operation for setting the results from a SimpleRead into the
    document's data from a data capture.

    This is a bit primative, but it is not obvious how to isolate the capturing
    functionality elsewhere."""

    descr = _("data capture")

    def __init__(self, simplereadobject):
        """Takes a simpleread object containing the data to be set."""
        self.simplereadobject = simplereadobject

    def do(self, doc):
        """Set the data in the document."""

        locked = doc._write_lock_holder == threading.current_thread().ident
        setdata = doc._setDataUnlocked if locked else doc.setData

        # set the data to the document and keep a list of what's changed
        readdata = {}
        self.simplereadobject.setOutput(readdata)

        # keep a copy of datasets which have changed from backup
        self.nameschanged = list(readdata)
        self.olddata = {}
        for name in self.nameschanged:
            if name in doc.data:
                self.olddata[name] = doc.data[name]
            setdata(name, readdata[name])

    def undo(self, doc):
        """Undo the results of the capture."""

        locked = doc._write_lock_holder == threading.current_thread().ident
        setdata = doc._setDataUnlocked if locked else doc.setData
        deldata = doc._deleteDataUnlocked if locked else doc.deleteData

        for name in self.nameschanged:
            if name in self.olddata:
                # replace datasets with what was there previously
                setdata(name, self.olddata[name])
            else:
                # or delete datasets that weren't there before
                deldata(name)

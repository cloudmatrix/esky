#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.sudo.sudo_base:  base functionality for esky sudo helpers

"""

import os
import sys
import errno
import base64
import struct
import signal
import subprocess
import tempfile
import hmac
from functools import wraps

try:
    import cPickle as pickle
except ImportError:
    import pickle

try:
    import threading
except ImportError:
    threading = None



def has_root():
    """Check whether the user currently has root access."""
    return False


def can_get_root():
    """Check whether the user may be able to get root access.

    This is currently always True on unix-like platforms, since we have no
    way of peering inside the sudoers file.
    """
    return True


class SecureStringPipe(object):
    """Two-way pipe for securely communicating strings with a sudo subprocess.

    This is the control pipe used for passing command data from the non-sudo
    master process to the sudo slave process.  Use read() to read the next
    string, write() to write the next string.

    As a security measure, all strings are "signed" using a rolling hmac based
    off a shared security token.  A bad signature results in the pipe being
    immediately closed and a RuntimeError being generated.
    """

    def __init__(self,token=None):
        if token is None:
            token = os.urandom(16)
        self.token = token
        self.connected = False

    def __del__(self):
        self.close()

    def connect(self):
        raise NotImplementedError

    def _read(self,size):
        raise NotImplementedError

    def _write(self,data):
        raise NotImplementedError

    def _open(self):
        raise NotImplementedError

    def _recover(self):
        pass

    def check_connection(self):
        if not self.connected:
            self._read_hmac = hmac.new(self.token)
            self._write_hmac = hmac.new(self.token)
            #timed_out = []
            #t = None
            #if threading is not None:
            #    def rescueme():
            #        timed_out.append(True)
            #        self._recover()
            #    t = threading.Timer(30,rescueme)
            #    t.start()
            self._open()
            #if timed_out:
            #    raise IOError(errno.ETIMEDOUT,"timed out during sudo")
            #elif t is not None:
            #    t.cancel()
            self.connected = True

    def close(self):
        self.connected = False

    def read(self):
        """Read the next string from the pipe.

        The expected data format is:  4-byte size, data, signature
        """
        self.check_connection()
        sz = self._read(4)
        if len(sz) < 4:
            raise EOFError
        sz = struct.unpack("I",sz)[0]
        data = self._read(sz)
        if len(data) < sz:
            raise EOFError
        sig = self._read(self._read_hmac.digest_size)
        self._read_hmac.update(data)
        if sig != self._read_hmac.digest():
            self.close()
            raise RuntimeError("mismatched hmac; terminating")
        return data

    def write(self,data):
        """Write the given string to the pipe.

        The expected data format is:  4-byte size, data, signature
        """
        self.check_connection()
        self._write(struct.pack("I",len(data)))
        self._write(data)
        self._write_hmac.update(data)
        self._write(self._write_hmac.digest())


def spawn_sudo(proxy):
    """Spawn the sudo slave process, returning proc and a pipe to message it."""
    raise NotImplementedError


def run_startup_hooks():
    raise NotImplementedError



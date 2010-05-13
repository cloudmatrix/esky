"""

  esky.helper.helper_unix:  platform-specific functionality for esky.helper

"""

import os
import sys
import errno
import base64
import struct
import signal
import subprocess
import tempfile
import itertools
from functools import wraps

try:
    import cPickle as pickle
except ImportError:
    import pickle


def pairwise(iterable):
    s1,s2 = itertools.tee(iterable)
    s2.next()
    return itertools.izip(s1,s2)


def has_root():
    """Check whether the use current has root access."""
    return False


class DuplexPipe(object):
    """A two-way pipe for communication with a subprocess.

    On unix this is implemented as a pair of anonymous pipes.
    """

    def __init__(self,data=None):
        if data is None:
            self.rfd,self.c_wfd = os.pipe()
            self.c_rfd,self.wfd = os.pipe()
        else:
            self.rfd,self.wfd = data
            self.c_rfd = self.c_wfd = None

    def connect(self):
        return DuplexPipe((self.c_rfd,self.c_wfd))

    def read(self,size):
        self._close_child_fds()
        data = os.read(self.rfd,size)
        return data

    def write(self,data):
        self._close_child_fds()
        return os.write(self.wfd,data)

    def _close_child_fds(self):
        if self.c_rfd is not None:
            os.close(self.c_rfd)
            self.c_rfd = None
        if self.c_wfd is not None:
            os.close(self.c_wfd)
            self.c_wfd = None

    def close(self):
        self._close_child_fds()
        os.close(self.rfd)
        os.close(self.wfd)


class SubprocPipe(object):
    """Pipe through which to communicate objects with a subprocess.

    This class provides simple inter-process communication of python objects,
    by pickling them and writing them to a pipe in a length-delimited format.
    """

    def __init__(self,proc,pipe):
        self.proc = proc
        self.pipe = pipe

    def read(self):
        """Read the next object from the pipe."""
        sz = self.pipe.read(4)
        if len(sz) < 4:
            raise EOFError
        sz = struct.unpack("I",sz)[0]
        data = self.pipe.read(sz)
        if len(data) < sz:
            raise EOFError
        return pickle.loads(data)

    def write(self,obj):
        """Write the given object to the pipe."""
        data = pickle.dumps(obj,pickle.HIGHEST_PROTOCOL)
        self.pipe.write(struct.pack("I",len(data)))
        self.pipe.write(data)

    def close(self):
        """Close the pipe."""
        self.pipe.close()

    def terminate(self):
        """Terminate the attached subprocess, if any."""
        if self.proc is not None:
            if hasattr(self.proc,"terminate"):
                self.proc.terminate()
            else:
                os.kill(self.proc.pid,signal.SIGTERM)


def find_helper():
    """Find the exe for the helper app."""
    if getattr(sys,"frozen",False):
        return [os.path.join(os.path.dirname(sys.executable),
                            "esky-update-helper")]
    return [sys.executable,"-m","esky.helper.__main__"]


def spawn_helper(as_root=False):
    """Spawn the helper app, returning a SubprocPipe connected to it."""
    rnul = open(os.devnull,"r")
    wnul = open(os.devnull,"w")
    p_pipe = DuplexPipe()
    c_pipe = p_pipe.connect()
    data = pickle.dumps(c_pipe,pickle.HIGHEST_PROTOCOL)
    exe = find_helper() + [base64.b64encode(data)]
    #  We want to close all file descriptors except those used in the
    #  pipe, so we roll our own preexec_fn to do so.
    def closefds():
        if hasattr(os,"closerange"):
            closerange = os.closerange
        else:
            def closerange(low,high):
                for i in xrange(low,high):
                    try:
                        os.close(i)
                    except OSError:
                        pass
        dontclose = [c_pipe.rfd,c_pipe.wfd,rnul.fileno(),wnul.fileno()]
        MAXFD = subprocess.MAXFD
        for (low,high) in pairwise(sorted(set([2] + dontclose + [MAXFD]))):
            closerange(low+1,high)
    kwds = dict(stdin=rnul,stdout=wnul,stderr=wnul,preexec_fn=closefds)
    p = subprocess.Popen(exe,**kwds)
    pipe = SubprocPipe(p,p_pipe)
    return pipe



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
    """Check whether the use current has root access."""
    return (os.geteuid() == 0)


def can_get_root():
    """Check whether the usee may be able to get root access.

    This is currently always True on unix-like platforms, since we have no
    way of peering inside the sudoers file.
    """
    return True


class DuplexPipe(object):
    """A two-way pipe for communication with a subprocess.

    On unix this is implemented via a pair of fifos.
    """

    def __init__(self,data=None):
        self.rfd = None
        self.wfd = None
        if data is None:
            self.tdir = tempfile.mkdtemp()
            self.rnm = os.path.join(self.tdir,"pipeout")
            self.wnm = os.path.join(self.tdir,"pipein")
            os.mkfifo(self.rnm,0600)
            os.mkfifo(self.wnm,0600)
        else:
            self.tdir,self.rnm,self.wnm = data

    def connect(self):
        return DuplexPipe((self.tdir,self.wnm,self.rnm))

    def read(self,size):
        if self.rfd is None:
            self.rfd = self._safely_open_pipe(self.rnm,os.O_RDONLY)
        data = os.read(self.rfd,size)
        return data

    def write(self,data):
        if self.wfd is None:
            self.wfd = self._safely_open_pipe(self.wnm,os.O_WRONLY)
        return os.write(self.wfd,data)

    def _safely_open_pipe(self,pipe,mode):
        """Open the pipe without hanging forever."""
        timed_out = []
        t = None
        if False and threading is not None:
            def rescueme():
                timed_out.append(True)
                if mode == os.O_RDONLY:
                    mymode = os.O_WRONLY
                else:
                    mymode = os.O_RDONLY
                try:
                    fd = os.open(pipe,mymode)
                except EnvironmentError:
                    pass
                else:
                    os.close(fd)
            t = threading.Timer(10,rescueme)
            t.start()
        fd = os.open(pipe,mode)
        if timed_out:
            raise IOError(errno.ETIMEDOUT,"timed out while opening pipe")
        elif t is not None:
            t.cancel()
        return fd

    def close(self):
        os.close(self.rfd)
        os.close(self.wfd)
        os.unlink(self.wnm)
        if not os.listdir(self.tdir):
            os.rmdir(self.tdir)


class SubprocPipe(object):
    """Pipe through which to communicate stringsd with a subprocess.

    This class provides simple inter-process communication of strings using
    a length-delimited format.
    """

    def __init__(self,proc,pipe):
        self.proc = proc
        self.pipe = pipe

    def read(self):
        """Read the next string from the pipe."""
        sz = self.pipe.read(4)
        if len(sz) < 4:
            raise EOFError
        sz = struct.unpack("I",sz)[0]
        data = self.pipe.read(sz)
        if len(data) < sz:
            raise EOFError
        return data

    def write(self,data):
        """Write the given string to the pipe."""
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


def find_exe(name,*args):
    path = os.environ.get("PATH","/bin:/usr/bin").split(":")
    if getattr(sys,"frozen",False):
        path.append(os.path.dirname(sys.executable))
    for dir in path:
        exe = os.path.join(dir,name)
        if os.path.exists(exe):
            return [exe] + list(args)
    return None


def spawn_helper(esky,as_root=False):
    """Spawn the helper app, returning a SubprocPipe connected to it."""
    rnul = open(os.devnull,"r")
    wnul = open(os.devnull,"w")
    p_pipe = DuplexPipe()
    c_pipe = p_pipe.connect()
    data = pickle.dumps(c_pipe,pickle.HIGHEST_PROTOCOL)
    exe = find_helper() + [base64.b64encode(data)]
    exe.append(base64.b64encode(pickle.dumps(esky)))
    #  Look for a variety of sudo-like programs
    if as_root:
        sudo = None
        display_name = "%s updater" % (esky.name,)
        if "DISPLAY" in os.environ:
            sudo = find_exe("gksudo","-k","-D",display_name,"--")
            if sudo is None:
                sudo = find_exe("kdesudo")
            if sudo is None:
                sudo = find_exe("cocoasudo","--prompt='%s'" % (display_name,))
        if sudo is None:
            sudo = find_exe("sudo")
        if sudo is not None:
            exe = sudo + exe
    #  Spawn the subprocess
    kwds = dict(stdin=rnul,stdout=wnul,stderr=wnul,close_fds=True)
    p = subprocess.Popen(exe,**kwds)
    pipe = SubprocPipe(p,p_pipe)
    return pipe



"""

  esky.helper:  stand-alone helper app for processing esky updates.


This module provides the infrastructure for spawning a stand-alone "helper app"
to install updates.  Such a helper app might be necessary because:

    * files need to be overwritten that are currently in use
    * the updates need to be performed with admin privileges

The EskyHelperApp class mirrors the filesystem-modifying methods an Esky, and
transparently proxies them to a running helper app:

    * cleanup()
    * fetch_version(v)
    * install_version(v)
    * uninstall_version(v)

It also has a "close" method that shuts down the proccess.

"""

import os
import sys
import errno
import base64
import struct
import subprocess
import tempfile
from functools import wraps

try:
    import cPickle as pickle
except ImportError:
    import pickle

if sys.platform != "win32":
    import signal
else:
    import uuid
    import ctypes
    kernel32 = ctypes.windll.kernel32
    byref = ctypes.byref
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    GENERIC_RDWR = GENERIC_READ | GENERIC_WRITE


#  Implement a simple "duplex pipe" that can be passed to subprocesses
#  without using file-handle inheritance.  This uses CreateNamedPipe on
#  win32 and a pair of FIFOs on unix.

if sys.platform == "win32":

    class DuplexPipe(object):
        """A two-way pipe for communication with a subprocess"""

        def __init__(self,data=None):
            self.connected = False
            if data is None:
                self.pipename = r"\\.\pipe\esky-" + uuid.uuid4().hex
                self.pipe = kernel32.CreateNamedPipeA(
                              self.pipename,0x03,0x00,1,8192,8192,0,None
                            )
            else:
                self.pipename = data
                self.pipe = None

        def connect(self):
            return DuplexPipe(self.pipename)

        def _open_pipe(self):
            self.pipe = kernel32.CreateFileA(
                self.pipename,GENERIC_RDWR,0x01|0x02,None,3,0,None
            )
            self.connected = True

        def read(self,size):
            if self.pipe is None:
               self._open_pipe()
            elif not self.connected:
                kernel32.ConnectNamedPipe(self.pipe,None)
            data = ctypes.create_string_buffer(size)
            szread = ctypes.c_int()
            kernel32.ReadFile(self.pipe,data,size,byref(szread),None)
            return data.raw[:szread.value]

        def write(self,data):
            if self.pipe is None:
               self._open_pipe()
            elif not self.connected:
                kernel32.ConnectNamedPipe(self.pipe,None)
            szread = ctypes.c_int()
            kernel32.WriteFile(self.pipe,data,len(data),byref(szread),None)

        def close(self):
            if self.pipe is not None:
                kernel32.CloseHandle(self.pipe)
 
else:

    class DuplexPipe(object):
        """A two-way pipe for communication with a subprocess."""

        def __init__(self,data=None):
            self.rfd = None
            self.wfd = None
            if data is None:
                self.tdir = tempfile.mkdtemp()
                self.p2c = os.path.join(self.tdir,"p2c")
                self.c2p = os.path.join(self.tdir,"c2p")
                os.mkfifo(self.p2c)
                os.mkfifo(self.c2p)
            else:
                self.tdir = data["tdir"]
                self.p2c = data["p2c"]
                self.c2p = data["c2p"]

        def connect(self):
            data = dict(tdir=self.tdir,p2c=self.c2p,c2p=self.p2c)
            return DuplexPipe(data)

        def read(self,size):
            if self.rfd is None:
                self.rfd = os.open(self.c2p,os.O_RDONLY)
            return os.read(self.rfd,size)

        def write(self,data):
            if self.wfd is None:
                self.wfd = os.open(self.p2c,os.O_WRONLY)
            return os.write(self.wfd,data)

        def close(self):
            if self.rfd is not None:
                os.close(self.rfd)
            if self.wfd is not None:
                os.close(self.wfd)
            os.unlink(self.p2c)
            if not os.listdir(self.tdir):
                os.rmdir(self.tdir)



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
            elif sys.platform == "win32":
                ctypes.windll.kernel32.TerminateProcess(self.proc._handle,-1)
            else:
                os.kill(self.proc.pid,signal.SIGTERM)


def spawn_helper(exe,as_administrator=False):
    """Spawn the helper app, returning a SubprocPipe connected to it."""
    if isinstance(exe,basestring):
        exe = [exe]
    rnul = open(os.devnull,"r")
    wnul = open(os.devnull,"w")
    pipe = DuplexPipe()
    data = pickle.dumps(pipe.connect(),pickle.HIGHEST_PROTOCOL)
    exe = exe + [base64.b64encode(data)]
    if sys.platform == "win32":
        kwds = dict(close_fds=True)
    else:
        kwds = dict(stdin=rnul,stdout=wnul,stderr=wnul,close_fds=True)
    p = subprocess.Popen(exe,**kwds)
    return SubprocPipe(p,pipe)


def proxied_method(func):
    @wraps(func)
    def proxied_method_wrapper(self,*args,**kwds):
        self.proc.write((func.func_name,args,kwds))
        (success,value) = self.proc.read()
        if not success:
            raise value
        else:
            return value
    return proxied_method_wrapper


class EskyHelperApp(object):
    """Proxy for spawning and interacting with a stand-along helper app."""

    def __init__(self,esky,as_administrator=False):
        if getattr(sys,"frozen",False):
            helper = os.path.join(os.path.dirname(sys.executable),
                                  "esky-update-helper")
            if sys.platform == "win32":
                helper += ".exe"
        else:
            helper = [sys.executable,"-m","esky.helper"]
        self.proc = spawn_helper(helper,as_administrator)
        self.proc.write(esky)
        if self.proc.read() != "READY":
            self.close()
            raise RuntimeError("failed to spawn helper app")

    def close(self):
        self.proc.write(("close",(),{}))
        self.proc.read()
        self.proc.close()

    @proxied_method
    def cleanup(self):
        pass

    @proxied_method
    def fetch_version(self,version):
        pass

    @proxied_method
    def install_version(self,version):
        pass

    @proxied_method
    def uninstall_version(self,version):
        pass


if __name__ == "__main__":
    pipe = SubprocPipe(None,pickle.loads(base64.b64decode(sys.argv[1])))
    try:
        esky = pipe.read()
        pipe.write("READY")
        while True:
            try:
                (method,args,kwds) = pipe.read()
                if method == "close":
                    pipe.write("CLOSING")
                else:
                    try:
                        res = getattr(esky,method)(*args,**kwds)
                    except Exception, e:
                        pipe.write((False,e))
                    else:
                        pipe.write((True,res))
            except EOFError:
                break
    finally:
        pipe.close()
    sys.exit(0)



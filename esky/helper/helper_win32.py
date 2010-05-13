"""

  esky.helper.helper_win32:  platform-specific functionality for esky.helper

"""

import os
import sys
import errno
import struct
import uuid
import base64
import ctypes
import subprocess

try:
    import cPickle as pickle
except ImportError:
    import pickle

byref = ctypes.byref
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
GENERIC_RDWR = GENERIC_READ | GENERIC_WRITE


def has_root():
    """Check whether the use current has root access."""
    return False


class DuplexPipe(object):
    """A two-way pipe for communication with a subprocess.

    On win32, this is implemented using CreateNamedPipe.
    """

    def __init__(self,data=None):
        self.connected = False
        if data is None:
            #  To prevent malicious processes trying to gain root through
            #  to helper app, we have the following safeguards on the pipe:
            #      * random name, not leaked until after creation
            #      * nMaxInstances set to 1 to prevent re-creation
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
                ctypes.windll.kernel32.TerminateProcess(self.proc._handle,-1)


def find_helper():
    """Find the exe for the helper app."""
    if getattr(sys,"frozen",False):
        return [os.path.join(os.path.dirname(sys.executable),
                            "esky-update-helper.exe")]
    return [sys.executable,"-m","esky.helper.__main__"]


def spawn_helper(as_root=True):
    """Spawn the helper app, returning a SubprocPipe connected to it.

    This function spawns the helper app, possibly as administrator, using
    ShellExecuteEx and the undocumented-but-widely-recommended "runas" verb.
    """
    pipe = DuplexPipe()
    data = pickle.dumps(pipe.connect(),pickle.HIGHEST_PROTOCOL)
    exe = find_helper() + [base64.b64encode(data)]
    p = subprocess.Popen(exe,close_fds=True)
    return SubprocPipe(p,pipe )


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
import struct
import subprocess
from functools import wraps

try:
    import cPickle as pickle
except ImportError:
    import pickle

if sys.platform == "win32":
    import msvcrt
    import _subprocess
    def duphandle(fd):
        curproc = _subprocess.GetCurrentProcess()
        h = msvcrt.get_osfhandle(fd)
        return _subprocess.DuplicateHandle(curproc,h,curproc,0,1,_subprocess.DUPLICATE_SAME_ACCESS).Detach()


class PicklePipe(object):
    """Pipe through which to send/receive pickled objects.

    This class provides simple inter-process communication of python objects,
    by pickling them and writing them to a pipe in a length-delimited format.
    """

    def __init__(self,r,w):
        self._rfd = r
        self._wfd = w

    def read(self):
        """Read the next object from the pipe."""
        sz = os.read(self._rfd,4)
        if len(sz) < 4:
            raise EOFError
        sz = struct.unpack("I",sz)
        data = os.read(self._rfd,sz)
        if len(data) < sz:
            raise EOFError
        return pickle.loads(data)

    def write(self,obj):
        """Write the given object to the pipe."""
        data = pickle.dumps(obj,pickle.HIGHEST_PROTOCOL)
        os.write(self._wfd,struct.pack("I",len(data)))
        os.write(self._wfd,data)

    def close(self):
        os.close(self._rfd)
        os.close(self._wfd)


def spawn_helper(exepath,as_administrator=False):
    """Spawn the helper app, returning read and write pipes."""
    
    rfd1,wfd1 = os.pipe()
    rfd2,wfd2 = os.pipe()
    if sys.platform != "win32":
        args = [rfd1,wfd2]
    else:
        args = [duphandle(rfd1),duphandle(wfd2)]
    os.close(rfd1)
    os.close(wfd2)
    p = subprocess.Popen([exepath]+args,stdin)
    return PicklePipe(rfd2,wfd2)


def proxied_method(func):
    @wraps(func)
    def proxied_method_wrapper(self,*args,**kwds):
        self._pipe.write((func.func_name,args,kwds))
        (success,value) = self._pipe.read()
        if not success:
            raise value
        else:
            return value
    return proxied_method_wrapper


class EskyHelperApp(object):
    """Proxy for spawning and interacting with a stand-along helper app."""

    def __init__(self,esky,as_administrator=False):
        #  Find the update helper executable.
        helper_exe = esky.name + "-update-helper"
        if sys.platform == "win32":
            helper_exe = helper_exe + ".exe"
        helper_exe = esky.get_abspath(helper_exe)
        self._pipe = spawn_helper(helper_exe,as_administrator)

    def close(self):
        self._pipe.write(("close",(),{}))
        self._pipe.read()
        self._pipe.close()

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
    esky = pickle.loads(sys.argv[1])
    pipe = PicklePipe(sys.argv[2],sys.argv[3])
    while True:
        try:
            (method,args,kwds) = pipe.read()
            if method == "close":
                pipe.write(None)
            else:
                try:
                    res = getattr(esky,method)(*args,**kwds)
                except Exception, e:
                    pipe.write((False,e))
                else:
                    pipe.write((True,res))
        except EOFError:
            break
    pipe.close()
    sys.exit(0)



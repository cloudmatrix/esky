#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.sudo.sudo_osx:  OSX platform-specific functionality for esky.sudo


This implementation of esky.sudo uses the native OSX Authorization framework
to spawn a helper with root privileges.

"""

import sys
if sys.platform != "darwin":
    raise ImportError("only usable on OSX")

import os
import errno
import struct
import signal
import subprocess
from base64 import b64encode, b64decode
from functools import wraps

from esky.sudo import sudo_base as base
import esky.slaveproc

pickle = base.pickle
HIGHEST_PROTOCOL = pickle.HIGHEST_PROTOCOL

import ctypes
import ctypes.util
from ctypes import byref

libc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("c"))
sec = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Security"))
try:
    sec.AuthorizationCreate
except AttributeError:
    raise ImportError("Security library not usable")

kAuthorizationFlagDefaults = 0
kAuthorizationFlagInteractionAllowed = (1 << 0)
kAuthorizationFlagExtendRights = (1 << 1)
kAuthorizationFlagPartialRights = (1 << 2)
kAuthorizationFlagDestroyRights = (1 << 3)
kAuthorizationFlagPreAuthorize = (1 << 4)
kAuthorizationFlagNoData = (1 << 20)

class AuthorizationRight(ctypes.Structure):
    _fields_ = [("name",ctypes.c_char_p),
                ("valueLength",ctypes.c_uint32),
                ("value",ctypes.c_void_p),
                ("flags",ctypes.c_uint32),
               ]

class AuthorizationRights(ctypes.Structure):
    _fields_ = [("count",ctypes.c_uint32),
                ("items",AuthorizationRight * 1)
               ]


def has_root():
    """Check whether the use current has root access."""
    return (os.geteuid() == 0)


def can_get_root():
    """Check whether the usee may be able to get root access.

    This is currently always True on unix-like platforms, since we have no
    way of peering inside the sudoers file.
    """
    return True


class FakePopen(subprocess.Popen):
    """Popen-esque class that's guaranteed killable, even on python2.5."""
    def __init__(self,pid):
        super(FakePopen,self).__init__(None)
        self.pid = pid
    def terminate(self):
        import signal
        os.kill(self.pid,signal.SIGTERM)
    def _execute_child(self,*args,**kwds):
        pass


class SecureStringPipe(base.SecureStringPipe):
    """A two-way pipe for securely communicating with a sudo subprocess.

    On OSX this is implemented by a FILE* object on the master end, and by
    stdin/stdout on the slave end.  Which is convenient, because that's just
    the thing that AuthorizationExecuteWithPrivileges gives us...
    """

    def __init__(self,token=None):
        super(SecureStringPipe,self).__init__(token)
        self.fp = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def connect(self):
        return SecureStringPipe(self.token)

    def _read(self,size):
        if self.fp is None:
            return os.read(0,size)
        else:
            buf = ctypes.create_string_buffer(size+2)
            read = libc.fread(byref(buf),1,size,self.fp)
            return buf.raw[:read]

    def _write(self,data):
        if self.fp is None:
            os.write(1,data)
        else:
            libc.fwrite(data,1,len(data),self.fp)

    def _open(self):
        pass

    def _recover(self):
        pass

    def close(self):
        if self.fp is not None:
            libc.fclose(self.fp)
            self.fp = None
        super(SecureStringPipe,self).close()


def spawn_sudo(proxy):
    """Spawn the sudo slave process, returning proc and a pipe to message it."""

    pipe = SecureStringPipe()
    c_pipe = pipe.connect()

    if not getattr(sys,"frozen",False):
        exe = [sys.executable,"-c","import esky; esky.run_startup_hooks()"]
    elif os.path.basename(sys.executable).lower() in ("python","pythonw"):
        exe = [sys.executable,"-c","import esky; esky.run_startup_hooks()"]
    else:
        if not esky._startup_hooks_were_run:
            raise OSError(None,"unable to sudo: startup hooks not run")
        exe = [sys.executable]
    args = ["--esky-spawn-sudo"]
    args.append(b64encode(pickle.dumps(proxy,HIGHEST_PROTOCOL)))
    args.append(b64encode(pickle.dumps(c_pipe,HIGHEST_PROTOCOL)))

    # Make it a slave process so it dies if we die
    exe = exe + esky.slaveproc.get_slave_process_args() + args

    auth = ctypes.c_void_p()

    right = AuthorizationRight()
    right.name = "py.esky.sudo." + proxy.name
    right.valueLength = 0
    right.value = None
    right.flags = 0

    rights = AuthorizationRights()
    rights.count = 1
    rights.items[0] = right

    r_auth = byref(auth)
    err = sec.AuthorizationCreate(None,None,kAuthorizationFlagDefaults,r_auth)
    if err:
        raise OSError(errno.EACCES,"could not sudo: %d" % (err,))

    try:

        kAuthFlags = kAuthorizationFlagDefaults \
                     | kAuthorizationFlagPreAuthorize \
                     | kAuthorizationFlagInteractionAllowed \
                     | kAuthorizationFlagExtendRights
        
        err = sec.AuthorizationCopyRights(auth,None,None,kAuthFlags,None)
        if err:
            raise OSError(errno.EACCES,"could not sudo: %d" % (err,))

        args = (ctypes.c_char_p * len(exe))()
        for i,arg in enumerate(exe[1:]):
            args[i] = arg
        args[len(exe)-1] = None
        io = ctypes.c_void_p()
        err = sec.AuthorizationExecuteWithPrivileges(auth,exe[0],0,args,byref(io))
        if err:
            raise OSError(errno.EACCES,"could not sudo: %d" %(err,))
        
        buf = ctypes.create_string_buffer(8)
        read = libc.fread(byref(buf),1,4,io)
        if read != 4:
            libc.fclose(io)
            raise OSError(errno.EACCES,"could not sudo: child failed")
        pid = struct.unpack("I",buf.raw[:4])[0]
        pipe.fp = io
        return (FakePopen(pid),pipe)
    finally:
        sec.AuthorizationFree(auth,kAuthorizationFlagDestroyRights)


def run_startup_hooks():
    if len(sys.argv) > 1 and sys.argv[1] == "--esky-spawn-sudo":
        if sys.version_info[0] > 2:
            proxy = pickle.loads(b64decode(sys.argv[2].encode("ascii")))
            pipe = pickle.loads(b64decode(sys.argv[3].encode("ascii")))
        else:
            proxy = pickle.loads(b64decode(sys.argv[2]))
            pipe = pickle.loads(b64decode(sys.argv[3]))
        os.write(1,struct.pack("I",os.getpid()))
        proxy.run(pipe)
        sys.exit(0)


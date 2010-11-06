#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.sudo.sudo_win32:  win32 platform-specific functionality for esky.sudo


This module implements the esky.sudo interface using ctypes bindings to the
native win32 API.  In particular, it uses the "runas" verb technique to
launch a process with administrative rights on Windows Vista and above.

"""

import os
import sys
import struct
import uuid
import ctypes
import ctypes.wintypes
import subprocess
from base64 import b64encode, b64decode

from esky.sudo import sudo_base as base
import esky.slaveproc

pickle = base.pickle
HIGHEST_PROTOCOL = pickle.HIGHEST_PROTOCOL


byref = ctypes.byref
sizeof = ctypes.sizeof
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32
advapi32 = ctypes.windll.advapi32

GENERIC_READ = -0x80000000
GENERIC_WRITE = 0x40000000
GENERIC_RDWR = GENERIC_READ | GENERIC_WRITE
OPEN_EXISTING = 3
TOKEN_QUERY = 8
SECURITY_MAX_SID_SIZE = 68
SECURITY_SQOS_PRESENT = 1048576
SECURITY_IDENTIFICATION = 65536
WinBuiltinAdministratorsSid = 26
ERROR_NO_SUCH_LOGON_SESSION = 1312
ERROR_PRIVILEGE_NOT_HELD = 1314
TokenLinkedToken = 19
SEE_MASK_NOCLOSEPROCESS = 0x00000040
SEE_MASK_NOASYNC  = 0x00000100


def _errcheck_bool(value,func,args):
    if not value:
        raise ctypes.WinError()
    return args

class SHELLEXECUTEINFO(ctypes.Structure):
    _fields_ = (
      ("cbSize",ctypes.wintypes.DWORD),
      ("fMask",ctypes.c_ulong),
      ("hwnd",ctypes.wintypes.HANDLE),
      ("lpVerb",ctypes.c_char_p),
      ("lpFile",ctypes.c_char_p),
      ("lpParameters",ctypes.c_char_p),
      ("lpDirectory",ctypes.c_char_p),
      ("nShow",ctypes.c_int),
      ("hInstApp",ctypes.wintypes.HINSTANCE),
      ("lpIDList",ctypes.c_void_p),
      ("lpClass",ctypes.c_char_p),
      ("hKeyClass",ctypes.wintypes.HKEY),
      ("dwHotKey",ctypes.wintypes.DWORD),
      ("hIconOrMonitor",ctypes.wintypes.HANDLE),
      ("hProcess",ctypes.wintypes.HANDLE),
    )


try:
    ShellExecuteEx = shell32.ShellExecuteEx
except AttributeError:
    ShellExecuteEx = None
else:
    ShellExecuteEx.restype = ctypes.wintypes.BOOL
    ShellExecuteEx.errcheck = _errcheck_bool
    ShellExecuteEx.argtypes = (
        ctypes.POINTER(SHELLEXECUTEINFO),
    )

try:
    OpenProcessToken = advapi32.OpenProcessToken
except AttributeError:
    pass
else:
    OpenProcessToken.restype = ctypes.wintypes.BOOL
    OpenProcessToken.errcheck = _errcheck_bool
    OpenProcessToken.argtypes = (
        ctypes.wintypes.HANDLE,
        ctypes.wintypes.DWORD,
        ctypes.POINTER(ctypes.wintypes.HANDLE)
    )

try:
    CreateWellKnownSid = advapi32.CreateWellKnownSid
except AttributeError:
    pass
else:
    CreateWellKnownSid.restype = ctypes.wintypes.BOOL
    CreateWellKnownSid.errcheck = _errcheck_bool
    CreateWellKnownSid.argtypes = (
        ctypes.wintypes.DWORD,
        ctypes.POINTER(ctypes.wintypes.DWORD),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.wintypes.DWORD)
    )

try:
    CheckTokenMembership = advapi32.CheckTokenMembership
except AttributeError:
    pass
else:
    CheckTokenMembership.restype = ctypes.wintypes.BOOL
    CheckTokenMembership.errcheck = _errcheck_bool
    CheckTokenMembership.argtypes = (
        ctypes.wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.wintypes.BOOL)
    )

try:
    GetTokenInformation = advapi32.GetTokenInformation
except AttributeError:
    pass
else:
    GetTokenInformation.restype = ctypes.wintypes.BOOL
    GetTokenInformation.errcheck = _errcheck_bool
    GetTokenInformation.argtypes = (
        ctypes.wintypes.HANDLE,
        ctypes.wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.wintypes.DWORD,
        ctypes.POINTER(ctypes.wintypes.DWORD)
    )



def has_root():
    """Check whether the user currently has root access."""
    return bool(shell32.IsUserAnAdmin())


def can_get_root():
    """Check whether the user may be able to get root access."""
    #  On XP or lower this is equivalent to has_root()
    if sys.getwindowsversion()[0] < 6:
        return bool(shell32.IsUserAnAdmin())
    #  On Vista or higher, there's the whole UAC token-splitting thing.
    #  Many thanks for Junfeng Zhang for the workflow:
    #      http://blogs.msdn.com/junfeng/archive/2007/01/26/how-to-tell-if-the-current-user-is-in-administrators-group-programmatically.aspx
    proc = kernel32.GetCurrentProcess()
    #  Get the token for the current process.
    try:
        token = ctypes.wintypes.HANDLE()
        OpenProcessToken(proc,TOKEN_QUERY,byref(token))
        try:
            #  Get the administrators SID.
            sid = ctypes.create_string_buffer(SECURITY_MAX_SID_SIZE)
            sz = ctypes.wintypes.DWORD(SECURITY_MAX_SID_SIZE)
            target_sid = WinBuiltinAdministratorsSid
            CreateWellKnownSid(target_sid,None,byref(sid),byref(sz))
            #  Check whether the token has that SID directly.
            has_admin = ctypes.wintypes.BOOL()
            CheckTokenMembership(None,byref(sid),byref(has_admin))
            if has_admin.value:
                return True
            #  Get the linked token.  Failure may mean no linked token.
            lToken = ctypes.wintypes.HANDLE()
            try:
                cls = TokenLinkedToken
                GetTokenInformation(token,cls,byref(lToken),sizeof(lToken),byref(sz))
            except WindowsError, e:
                if e.winerror == ERROR_NO_SUCH_LOGON_SESSION:
                    return False
                elif e.winerror == ERROR_PRIVILEGE_NOT_HELD:
                    return False
                else:
                    raise
            #  Check if the linked token has the admin SID
            try:
                CheckTokenMembership(lToken,byref(sid),byref(has_admin))
                return bool(has_admin.value)
            finally:
                kernel32.CloseHandle(lToken)
        finally:
            kernel32.CloseHandle(token)
    finally:
        kernel32.CloseHandle(proc)



class KillablePopen(subprocess.Popen):
    """Popen that's guaranteed killable, even on python2.5."""
    if not hasattr(subprocess.Popen,"terminate"):
        def terminate(self):
            kernel32.TerminateProcess(self._handle,-1)


class FakePopen(KillablePopen):
    """Popen-alike based on a raw process handle."""
    def __init__(self,handle):
        super(FakePopen,self).__init__(None)
        self._handle = handle
    def terminate(self):
        kernel32.TerminateProcess(self._handle,-1)
    def _execute_child(self,*args,**kwds):
        pass
    

class SecureStringPipe(base.SecureStringPipe):
    """Two-way pipe for securely communicating strings with a sudo subprocess.

    This is the control pipe used for passing command data from the non-sudo
    master process to the sudo slave process.  Use read() to read the next
    string, write() to write the next string.

    On win32, this is implemented using CreateNamedPipe in the non-sudo
    master process, and connecting to the pipe from the sudo slave process.

    Security considerations to prevent hijacking of the pipe:

        * it has a strongly random name, so there can be no race condition
          before the pipe is created.
        * it has nMaxInstances set to 1 so another process cannot spoof the
          pipe while we are still alive.
        * the slave connects with pipe client impersonation disabled.

    A possible attack vector would be to wait until we spawn the slave process,
    capture the name of the pipe, then kill us and re-create the pipe to become
    the new master process.  Not sure what can be done about this, but at the
    very worst this will allow the attacker to call into the esky API with
    root privs; it *shouldn't* be sufficient to crack root on the machine...
    """

    def __init__(self,token=None,pipename=None):
        super(SecureStringPipe,self).__init__(token)
        if pipename is None:
            self.pipename = r"\\.\pipe\esky-" + uuid.uuid4().hex
            self.pipe = kernel32.CreateNamedPipeA(
                          self.pipename,0x03,0x00,1,8192,8192,0,None
                        )
        else:
            self.pipename = pipename
            self.pipe = None

    def connect(self):
        return SecureStringPipe(self.token,self.pipename)

    def _read(self,size):
        data = ctypes.create_string_buffer(size)
        szread = ctypes.c_int()
        kernel32.ReadFile(self.pipe,data,size,byref(szread),None)
        return data.raw[:szread.value]

    def _write(self,data):
        szwritten = ctypes.c_int()
        kernel32.WriteFile(self.pipe,data,len(data),byref(szwritten),None)

    def close(self):
        if self.pipe is not None:
            kernel32.CloseHandle(self.pipe)
            self.pipe = None
        super(SecureStringPipe,self).close()

    def _open(self):
        if self.pipe is None:
            self.pipe = kernel32.CreateFileA(
                self.pipename,GENERIC_RDWR,0,None,OPEN_EXISTING,
                SECURITY_SQOS_PRESENT|SECURITY_IDENTIFICATION,None
            )
        else:
            kernel32.ConnectNamedPipe(self.pipe,None)

    def _recover(self):
        kernel32.CreateFileA(
            self.pipename,GENERIC_RDWR,0,None,OPEN_EXISTING,
            SECURITY_SQOS_PRESENT|SECURITY_IDENTIFICATION,None
        )


def spawn_sudo(proxy):
    """Spawn the sudo slave process, returning proc and a pipe to message it.

    This function spawns the proxy app with administrator privileges, using
    ShellExecuteEx and the undocumented-but-widely-recommended "runas" verb.
    """
    pipe = SecureStringPipe()
    c_pipe = pipe.connect()
    if getattr(sys,"frozen",False):
        if not esky._startup_hooks_were_run:
            raise OSError(None,"unable to sudo: startup hooks not run")
        exe = [sys.executable]
    else:
        exe = [sys.executable,"-c","import esky; esky.run_startup_hooks()"]
    args = ["--esky-spawn-sudo"]
    args.append(b64encode(pickle.dumps(proxy,HIGHEST_PROTOCOL)))
    args.append(b64encode(pickle.dumps(c_pipe,HIGHEST_PROTOCOL)))
    # Make it a slave process so it dies if we die
    exe = exe + esky.slaveproc.get_slave_process_args() + args
    if sys.getwindowsversion()[0] < 6:
        kwds = {}
        if sys.hexversion >= 0x20600000:
            kwds["close_fds"] = True
        proc = KillablePopen(exe,**kwds)
    else:
        execinfo = SHELLEXECUTEINFO()
        execinfo.cbSize = sizeof(execinfo)
        execinfo.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
        execinfo.hwnd = None
        execinfo.lpVerb = "runas"
        execinfo.lpFile = exe[0]
        execinfo.lpParameters = " ".join(exe[1:])
        execinfo.lpDirectory = None
        execinfo.nShow = 0
        ShellExecuteEx(byref(execinfo))
        proc = FakePopen(execinfo.hProcess)
    return (proc,pipe)


def run_startup_hooks():
    if len(sys.argv) > 1 and sys.argv[1] == "--esky-spawn-sudo":
        proxy = pickle.loads(b64decode(sys.argv[2]))
        pipe = pickle.loads(b64decode(sys.argv[3]))
        proxy.run(pipe)
        sys.exit(0)



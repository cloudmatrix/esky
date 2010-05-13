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
import ctypes.wintypes
import subprocess

try:
    import cPickle as pickle
except ImportError:
    import pickle

byref = ctypes.byref
sizeof = ctypes.sizeof
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32
advapi32 = ctypes.windll.advapi32

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
GENERIC_RDWR = GENERIC_READ | GENERIC_WRITE
TOKEN_QUERY = 8
SECURITY_MAX_SID_SIZE = 68
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

def _errcheck_handle(value,func,args):
    if not value:
        raise ctypes.WinError()
    if value == INVALID_HANDLE_VALUE:
        raise ctypes.WinError()
    return args

def _errcheck_dword(value,func,args):
    if value == 0xFFFFFFFF:
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
    #  On XP or lower this is equivalent to has_root().
    if sys.getwindowsversion()[0] < 6:
        return bool(shell32.IsUserAnAdmin())
    #  On Vista or higher, there's whole UAC token-splitting thing.
    #  Many thanks for Junfeng Zhang for the workflow:
    #      http://blogs.msdn.com/junfeng/archive/2007/01/26/how-to-tell-if-the-current-user-is-in-administrators-group-programmatically.aspx
    #
    #  Get the token for the current process.
    proc = kernel32.GetCurrentProcess()
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
                if e.errno == ERROR_NO_SUCH_LOGON_SESSION:
                    return False
                elif e.errno == ERROR_PRIVILEGE_NOT_HELD:
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
    """Pipe through which to communicate strings with a subprocess.

    This class provides simple inter-process communication of strings in a
    length-delimited format.
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
                ctypes.windll.kernel32.TerminateProcess(self.proc._handle,-1)


def find_helper():
    """Find the exe for the helper app."""
    if getattr(sys,"frozen",False):
        return [os.path.join(os.path.dirname(sys.executable),
                            "esky-update-helper.exe")]
    return [sys.executable,"-m","esky.helper.__main__"]


class FakePopen:
    def __init__(self,handle):
        self._handle = handle


def spawn_helper(esky,as_root=True):
    """Spawn the helper app, returning a SubprocPipe connected to it.

    This function spawns the helper app, possibly as administrator, using
    ShellExecuteEx and the undocumented-but-widely-recommended "runas" verb.
    """
    pipe = DuplexPipe()
    data = pickle.dumps(pipe.connect(),pickle.HIGHEST_PROTOCOL)
    exe = find_helper() + [base64.b64encode(data)]
    exe.append(base64.b64encode(pickle.dumps(esky)))
    if not as_root or  sys.getwindowsversion()[0] < 6:
        p = subprocess.Popen(exe,close_fds=True)
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
        p = FakePopen(execinfo.hProcess)
    return SubprocPipe(p,pipe )


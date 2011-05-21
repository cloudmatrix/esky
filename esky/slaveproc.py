#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.slaveproc:  utilities for running a slave process.

A "slave process" is one that automatically dies when its master process dies.
To implement this, the slave process spins up a background thread that watches
the parent and calls os._exit(1) if it dies.

On unix, the master process takes an exclusive flock on a temporary file, which
will disappear when the master dies.  The slave process can do a blocking 
acquire on this lock to wait for the master to die.

On windows, the master process creates a file with O_TEMPORARY, which will
disappear when the master dies.  The slave process can use ReadDirectoryChanges
to watch for the disappearance of this file.

"""

from __future__ import absolute_import

import sys

from esky.util import lazy_import


@lazy_import
def os():
    import os
    return os

@lazy_import
def tempfile():
    import tempfile
    return tempfile

@lazy_import
def threading():
    try:
        import threading
    except ImportError:
        threading = None
    return threading

@lazy_import
def ctypes():
    import ctypes
    import ctypes.wintypes
    return ctypes


def monitor_master_process(fpath):
    """Watch the given path to detect the master process dying.

    If the master process dies, the current process is terminated.
    """
    if not threading:
        return None
    def monitor():
        if wait_for_master(fpath):
            os._exit(1)
    t = threading.Thread(target=monitor)
    t.daemon = True
    t.start()
    return t


def get_slave_process_args():
    """Get the arguments that should be passed to a new slave process."""


def run_startup_hooks():
    if len(sys.argv) > 1 and sys.argv[1] == "--esky-slave-proc":
        del sys.argv[1]
        if len(sys.argv) > 1:
            arg = sys.argv[1]
            del sys.argv[1]
        else:
            arg = None
        monitor_master_process(arg)


if sys.platform == "win32":

    #  On win32, the master process creates a tempfile that will be deleted
    #  when it exits.  Use ReadDirectoryChanges to block on this event.

    def wait_for_master(fpath):
        """Wait for the master process to die."""
        try:
            RDCW = ctypes.windll.kernel32.ReadDirectoryChangesW
        except AttributeError:
            return False

        INVALID_HANDLE_VALUE = 0xFFFFFFFF
        FILE_NOTIFY_CHANGE_FILE_NAME = 0x01

        FILE_LIST_DIRECTORY = 0x01
        FILE_SHARE_READ = 0x01
        FILE_SHARE_WRITE = 0x02
        OPEN_EXISTING = 3
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

        try:
            ctypes.wintypes.LPVOID
        except AttributeError:
            ctypes.wintypes.LPVOID = ctypes.c_void_p

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

        RDCW.errcheck = _errcheck_bool
        RDCW.restype = ctypes.wintypes.BOOL
        RDCW.argtypes = (
            ctypes.wintypes.HANDLE, # hDirectory
            ctypes.wintypes.LPVOID, # lpBuffer
            ctypes.wintypes.DWORD, # nBufferLength
            ctypes.wintypes.BOOL, # bWatchSubtree
            ctypes.wintypes.DWORD, # dwNotifyFilter
            ctypes.POINTER(ctypes.wintypes.DWORD), # lpBytesReturned
            ctypes.wintypes.LPVOID, # lpOverlapped
            ctypes.wintypes.LPVOID  # lpCompletionRoutine
        )

        CreateFileW = ctypes.windll.kernel32.CreateFileW
        CreateFileW.errcheck = _errcheck_handle
        CreateFileW.restype = ctypes.wintypes.HANDLE
        CreateFileW.argtypes = (
            ctypes.wintypes.LPCWSTR, # lpFileName
            ctypes.wintypes.DWORD, # dwDesiredAccess
            ctypes.wintypes.DWORD, # dwShareMode
            ctypes.wintypes.LPVOID, # lpSecurityAttributes
            ctypes.wintypes.DWORD, # dwCreationDisposition
            ctypes.wintypes.DWORD, # dwFlagsAndAttributes
            ctypes.wintypes.HANDLE # hTemplateFile
        )

        CloseHandle = ctypes.windll.kernel32.CloseHandle
        CloseHandle.restype = ctypes.wintypes.BOOL
        CloseHandle.argtypes = (
            ctypes.wintypes.HANDLE, # hObject
        )

        result = ctypes.create_string_buffer(1024)
        nbytes = ctypes.c_ulong()
        handle = CreateFileW(os.path.join(os.path.dirname(fpath),u""),
                             FILE_LIST_DIRECTORY,
                             FILE_SHARE_READ | FILE_SHARE_WRITE,
                             None,
                             OPEN_EXISTING,
                             FILE_FLAG_BACKUP_SEMANTICS,
                             0
                 )

        #  Since this loop may still be running at interpreter close, we
        #  take local references to our imported functions to avoid
        #  garbage-collection-related errors at shutdown.
        byref = ctypes.byref
        pathexists = os.path.exists

        try:
            while pathexists(fpath):
                RDCW(handle,byref(result),len(result),
                     True,FILE_NOTIFY_CHANGE_FILE_NAME,
                     byref(nbytes),None,None)
        finally:
            CloseHandle(handle)
        return True

    def get_slave_process_args():
        """Get the arguments that should be passed to a new slave process."""
        try:
            flags = os.O_CREAT|os.O_EXCL|os.O_TEMPORARY|os.O_NOINHERIT
            tfile = tempfile.mktemp()
            fd = os.open(tfile,flags)
        except EnvironmentError:
            return []
        else:
            return ["--esky-slave-proc",tfile]
             

else:

    #  On unix, the master process takes an exclusive flock on the given file.
    #  We try to take one as well, which will block until the master dies.

    import fcntl

    def wait_for_master(fpath):
        """Wait for the master process to die."""
        try:
            fd = os.open(fpath,os.O_RDWR)
            fcntl.flock(fd,fcntl.LOCK_EX)
            return True
        except EnvironmentError:
            return False

    def get_slave_process_args():
        """Get the arguments that should be passed to a new slave process."""
        try:
            (fd,tfile) = tempfile.mkstemp()
            fcntl.flock(fd,fcntl.LOCK_EX)
        except EnvironmentError:
            return []
        else:
            return ["--esky-slave-proc",tfile]



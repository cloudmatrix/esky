#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.fstransact.win32fxt:  win32 transactional filesystem operations

"""


import os
import sys
import errno
import shutil

from esky.util import get_backup_filename, files_differ

if sys.platform != "win32":
    raise ImportError("win32fxt only available on win32 platform")

def check_call(func):
    def wrapper(*args,**kwds):
        res = func(*args,**kwds)
        if not res or res == 0xFFFFFFFF or res == -1:
            raise ctypes.WinError()
        return res
    return wrapper


try:
    import ctypes
    ktmw32 = ctypes.windll.ktmw32
    CreateTransaction = check_call(ktmw32.CreateTransaction)
    CommitTransaction = check_call(ktmw32.CommitTransaction)
    RollbackTransaction = check_call(ktmw32.RollbackTransaction)
    kernel32 = ctypes.windll.kernel32
    MoveFileTransacted = check_call(kernel32.MoveFileTransactedA)
    CopyFileTransacted = check_call(kernel32.CopyFileTransactedA)
    DeleteFileTransacted = check_call(kernel32.DeleteFileTransactedA)
    RemoveDirectoryTransacted = check_call(kernel32.RemoveDirectoryTransactedA)
    CreateDirectoryTransacted = check_call(kernel32.CreateDirectoryTransactedA)
except (WindowsError,AttributeError):
    raise ImportError("win32 TxF is not available")


ERROR_TRANSACTIONAL_OPEN_NOT_ALLOWED = 6832


class FSTransaction(object):
    """Utility class for transactionally operating on the filesystem.

    This particular implementation uses the transaction services provided
    by Windows Vista and later (from ktmw32.dll).
    """

    def __init__(self,root=None):
        if root is None:
            self.root = None
        else:
            self.root = os.path.normpath(os.path.abspath(root))
            if self.root.endswith(os.sep):
                self.root = self.root[:-1]
        self.trnid = CreateTransaction(None,0,0,0,0,None,"")
        self._check_root()

    def _check_root(self):
        if self.root is not None:
            #  Verify that files under the given root can actually be
            #  operated on transactionally.  We do this by trying to move
            #  the root directory to itself.  This should always fail, but
            #  will fail with a transaction error if they're not supported.
            try:
                self._move(self.root,self.root)
            except WindowsError, e:
                if e.winerror == ERROR_TRANSACTIONAL_OPEN_NOT_ALLOWED:
                    raise
            finally:
                self.abort()
            self.trnid = CreateTransaction(None,0,0,0,0,None,"")
        
    def _check_path(self,path):
        if self.root is not None:
            path = os.path.normpath(os.path.join(self.root,path))
            if len(self.root) == 2:
                prefix = self.root
            else:
                prefix = self.root + os.sep
            if not path.startswith(prefix):
                err = "path is outside transaction root: %s" % (path,)
                raise ValueError(err)
        return path

    def move(self,source,target):
        source = self._check_path(source)
        target = self._check_path(target)
        if os.path.isdir(source):
            if os.path.isdir(target):
                s_names = os.listdir(source)
                for nm in s_names:
                    self.move(os.path.join(source,nm),
                              os.path.join(target,nm))
                for nm in os.listdir(target):
                    if nm not in s_names:
                        self._remove(os.path.join(target,nm))
                self._remove(source)
            else:
                self._move(source,target)
        else:
            if os.path.isdir(target) or files_differ(source,target):
                self._move(source,target)
            else:
                self._remove(source)

    def _move(self,source,target):
        source = source.encode(sys.getfilesystemencoding())
        target = target.encode(sys.getfilesystemencoding())
        if os.path.exists(target) and target != source:
            target_old = get_backup_filename(target)
            MoveFileTransacted(target,target_old,None,None,1,self.trnid)
            MoveFileTransacted(source,target,None,None,1,self.trnid)
            try:
                self._remove(target_old)
            except EnvironmentError:
                pass
        else:
            self._create_parents(target)
            MoveFileTransacted(source,target,None,None,1,self.trnid)

    def _create_parents(self,target):
        parents = [target]
        while not os.path.exists(os.path.dirname(parents[-1])):
            parents.append(os.path.dirname(parents[-1]))
            if not parents[-1]:
                parents = parents[:-1]
                break
        for parent in reversed(parents[1:]):
            try:
                CreateDirectoryTransacted(None,parent,0,self.trnid)
            except WindowsError, e:
                if e.winerror != 183:
                    raise

    def copy(self,source,target):
        source = self._check_path(source)
        target = self._check_path(target)
        if os.path.isdir(source):
            if os.path.isdir(target):
                s_names = os.listdir(source)
                for nm in s_names:
                    self.copy(os.path.join(source,nm),
                              os.path.join(target,nm))
                for nm in os.listdir(target):
                    if nm not in s_names:
                        self._remove(os.path.join(target,nm))
            else:
                self._copy(source,target)
        else:
            if os.path.isdir(target) or files_differ(source,target):
                self._copy(source,target)

    def _copy(self,source,target):
        source = source.encode(sys.getfilesystemencoding())
        target = target.encode(sys.getfilesystemencoding())
        if os.path.exists(target) and target != source:
            target_old = get_backup_filename(target)
            MoveFileTransacted(target,target_old,None,None,1,self.trnid)
            self._do_copy(source,target)
            try:
                self._remove(target_old)
            except EnvironmentError:
                pass
        else:
            target_old = None
            if os.path.isdir(target) and target != source:
                target_old = get_backup_filename(target)
                MoveFileTransacted(target,target_old,None,None,1,self.trnid)
            self._do_copy(source,target)
            if target_old is not None:
                self._remove(target_old)

    def _do_copy(self,source,target):
        self._create_parents(target)
        if os.path.isdir(source):
            CreateDirectoryTransacted(None,target,0,self.trnid)
            for nm in os.listdir(source):
                self._do_copy(os.path.join(source,nm),
                              os.path.join(target,nm))
        else:
            CopyFileTransacted(source,target,None,None,None,0,self.trnid)

    def remove(self,target):
        target = self._check_path(target)
        self._remove(target)

    def _remove(self,target):
        target = target.encode(sys.getfilesystemencoding())
        if os.path.isdir(target):
            for nm in os.listdir(target):
                self.remove(os.path.join(target,nm))
            try:
                RemoveDirectoryTransacted(target,self.trnid)
            except EnvironmentError, e:
                if e.errno != errno.ENOENT:
                    raise
        else:
            try:
                DeleteFileTransacted(target,self.trnid)
            except EnvironmentError, e:
                if e.errno != errno.ENOENT:
                    raise

    def commit(self):
        CommitTransaction(self.trnid)

    def abort(self):
        RollbackTransaction(self.trnid)



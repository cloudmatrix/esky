#  Copyright (c) 2009, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.fstransact: best-effort support for transactional filesystem operations

This module provides a uniform interface to various platform-specific 
mechanisms for doing transactional filesystem operations.  On platforms where
transactions are not supported, it falls back to doing things one operation
at a time.

Currently supported platforms are:

    * Windows Vista and later, using MoveFileTransacted and friends
    * err..that's it for the moment, actually

Although transactions are not supported on POSIX platforms, the way Esky
structures its filesystem operations means that the program is always safe
as long as you can atomically replace a file.

"""

import sys
import shutil
import os

#  Try to access the transacted filesystem APIs on win32
CreateTransaction = None
if sys.platform == "win32":
    try:
        import ctypes
    except ImportError:
        pass
    else:
        try:
            ktmw32 = ctypes.windll.ktmw32
            CreateTransaction = ktmw32.CreateTransaction
            CommitTransaction = ktmw32.CommitTransaction
            RollbackTransaction = ktmw32.RollbackTransaction
            kernel32 = ctypes.windll.kernel32
            MoveFileTransacted = kernel32.MoveFileTransactedA
            CopyFileTransacted = kernel32.CopyFileTransactedA
            DeleteFileTransacted = kernel32.DeleteFileTransactedA
            RemoveDirectoryTransacted = kernel32.RemoveDirectoryTransactedA
            CreateDirectoryTransacted = kernel32.CreateDirectoryTransactedA
        except (WindowsError,AttributeError):
            CreateTransaction = None


def files_differ(file1,file2):
    """Check whether two files are actually different."""
    try:
        stat1 = os.stat(file1)
        stat2 = os.stat(file2)
    except EnvironmentError:
         return True
    if stat1.st_size != stat2.st_size:
        return True
    assert not os.path.isdir(file1)
    assert not os.path.isdir(file2)
    f1 = open(file1,"rb")
    try:
        f2 = open(file2,"rb")
        try:
            data1 = f1.read(1024*256)
            data2 = f2.read(1024*256)
            while data1 and data2:
                if data1 != data2:
                    return True
                data1 = f1.read(1024*256)
                data2 = f2.read(1024*256)
            return (data1 != data2)
        finally:
            f2.close()
    finally:
        f1.close()


if CreateTransaction:

    class FSTransaction(object):
        """Utility class for transactionally operating on the filesystem.

        This particular implementation uses the transaction services provided
        by Windows Vista and later (from ktmw32.dll).
        """

        def __init__(self):
            self.trnid = CreateTransaction(None,0,0,0,0,None,"")

        def move(self,source,target):
            if os.path.isdir(source):
                if os.path.isdir(target):
                    s_names = os.listdir(source)
                    for nm in s_names:
                        self.move(os.path.join(source,nm),
                                  os.path.join(target,nm))
                    for nm in os.listdir(target):
                        if nm not in s_names:
                            self.remove(os.path.join(target,nm))
                    self.remove(source)
                else:
                    self._move(source,target)
            else:
                if os.path.isdir(target) or files_differ(source,target):
                    self._move(source,target)
                else:
                    self.remove(source)

        def _move(self,source,target):
            source = source.encode(sys.getfilesystemencoding())
            target = target.encode(sys.getfilesystemencoding())
            if os.path.exists(target):
                target_old = target + ".old"
                while os.path.exists(target_old):
                    target_old += ".old"
                MoveFileTransacted(target,target_old,None,None,1,self.trnid)
                MoveFileTransacted(source,target,None,None,1,self.trnid)
                try:
                    self.remove(target_old)
                except EnvironmentError:
                    pass
            else:
                MoveFileTransacted(source,target,None,None,1,self.trnid)

        def copy(self,source,target):
            if os.path.isdir(source):
                if os.path.isdir(target):
                    s_names = os.listdir(source)
                    for nm in s_names:
                        self.copy(os.path.join(source,nm),
                                  os.path.join(target,nm))
                    for nm in os.listdir(target):
                        if nm not in s_names:
                            self.remove(os.path.join(target,nm))
                else:
                    self._copy(source,target)
            else:
                if os.path.isdir(target) or files_differ(source,target):
                    self._copy(source,target)

        def _copy(self,source,target):
            source = source.encode(sys.getfilesystemencoding())
            target = target.encode(sys.getfilesystemencoding())
            if os.path.exists(target):
                target_old = target + ".old"
                while os.path.exists(target_old):
                    target_old += ".old"
                MoveFileTransacted(target,target_old,None,None,1,self.trnid)
                self._do_copy(source,target)
                try:
                    self.remove(target_old)
                except EnvironmentError:
                    pass
            else:
                target_old = None
                if os.path.isdir(target):
                    target_old = target + ".old"
                    while os.path.exists(target_old):
                        target_old += ".old"
                    MoveFileTransacted(target,target_old,None,None,1,self.trnid)
                self._do_copy(source,target)
                if target_old is not None:
                    self.remove(target_old)

        def _do_copy(self,source,target):
            if os.path.isdir(source):
                CreateDirectoryTransacted(None,target,0,self.trnid)
                for nm in os.listdir(source):
                    self._do_copy(os.path.join(source,nm),
                                  os.path.join(target,nm))
            else:
                CopyFileTransacted(source,target,None,None,None,0,self.trnid)

        def remove(self,target):
            target = target.encode(sys.getfilesystemencoding())
            if os.path.isdir(target):
                for nm in os.listdir(target):
                    self.remove(os.path.join(target,nm))
                RemoveDirectoryTransacted(target,self.trnid)
            else:
                DeleteFileTransacted(target,self.trnid)

        def commit(self):
            CommitTransaction(self.trnid)

        def abort(self):
            RollbackTransaction(self.trnid)

else:

    class FSTransaction(object):
        """Utility class for transactionally operating on the filesystem.

        This particular implementation is the fallback for systems that don't
        support transactional filesystem operations.
        """

        def __init__(self):
            self.pending = []

        def move(self,source,target):
            if os.path.isdir(source):
                if os.path.isdir(target):
                    s_names = os.listdir(source)
                    for nm in s_names:
                        self.move(os.path.join(source,nm),
                                  os.path.join(target,nm))
                    for nm in os.listdir(target):
                        if nm not in s_names:
                            self.remove(os.path.join(target,nm))
                    self.remove(source)
                else:
                    self.pending.append(("_move",source,target))
            else:
                if os.path.isdir(target) or files_differ(source,target):
                    self.pending.append(("_move",source,target))
                else:
                    self.pending.append(("_remove",source))

        def _move(self,source,target):
            if sys.platform == "win32" and os.path.exists(target):
                #  os.rename won't overwite an existing file on win32.
                #  We also want to use this on files that are potentially open.
                #  Renaming the target out of the way is the best we can do :-(
                target_old = target + ".old"
                while os.path.exists(target_old):
                    target_old = target_old + ".old"
                os.rename(target,target_old)
                try:
                    os.rename(source,target)
                except:
                    os.rename(target_old,target)
                    raise
                else:
                    try:
                        self._remove(target_old)
                    except EnvironmentError:
                        pass
            else:
                target_old = None
                if os.path.isdir(target) and os.path.isfile(source):
                    target_old = target + ".old"
                    while os.path.exists(target_old):
                        target_old = target_old + ".old"
                    os.rename(target,target_old)
                elif os.path.isfile(target) and os.path.isdir(source):
                    target_old = target + ".old"
                    while os.path.exists(target_old):
                        target_old = target_old + ".old"
                    os.rename(target,target_old)
                os.rename(source,target)
                if target_old is not None:
                    self._remove(target_old)

        def copy(self,source,target):
            if os.path.isdir(source):
                if os.path.isdir(target):
                    s_names = os.listdir(source)
                    for nm in s_names:
                        self.copy(os.path.join(source,nm),
                                  os.path.join(target,nm))
                    for nm in os.listdir(target):
                        if nm not in s_names:
                            self.remove(os.path.join(target,nm))
                else:
                    self.pending.append(("_copy",source,target))
            else:
                if os.path.isdir(target) or files_differ(source,target):
                    self.pending.append(("_copy",source,target))

        def _copy(self,source,target):
            if sys.platform == "win32" and os.path.exists(target):
                target_old = target + ".old"
                while os.path.exists(target_old):
                    target_old = target_old + ".old"
                os.rename(target,target_old)
                try:
                    self._do_copy(source,target)
                except:
                    os.rename(target_old,target)
                    raise
                else:
                    try:
                        os.unlink(target_old)
                    except EnvironmentError:
                        pass
            else:
                target_old = None
                if os.path.isdir(target) and os.path.isfile(source):
                    target_old = target + ".old"
                    while os.path.exists(target_old):
                        target_old = target_old + ".old"
                    os.rename(target,target_old)
                elif os.path.isfile(target) and os.path.isdir(source):
                    target_old = target + ".old"
                    while os.path.exists(target_old):
                        target_old = target_old + ".old"
                    os.rename(target,target_old)
                self._do_copy(source,target)
                if target_old is not None:
                    self._remove(target_old)

        def _do_copy(self,source,target):
            if os.path.isfile(source):
                shutil.copy2(source,target)
            else:
                shutil.copytree(source,target)

        def remove(self,target):
            self.pending.append(("_remove",target))

        def _remove(self,target):
            if os.path.isfile(target):
                os.unlink(target)
            elif os.path.isdir(target):
                for nm in os.listdir(target):
                    self._remove(os.path.join(target,nm))
                os.rmdir(target)

        def commit(self):
            for op in self.pending:
                getattr(self,op[0])(*op[1:])

        def abort(self):
            del self.pending[:]


#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.fstransact.fallback: fallback implementation for FSTransaction

"""

import os
import sys
import shutil

from esky.util import get_backup_filename, files_differ, really_rename


class FSTransaction(object):
    """Utility class for transactionally operating on the filesystem.

    This particular implementation is the fallback for systems that don't
    support transactional filesystem operations.
    """

    def __init__(self,root=None):
        if root is None:
            self.root = None
        else:
            self.root = os.path.normpath(os.path.abspath(root))
            if self.root.endswith(os.sep):
                self.root = self.root[:-1]
        self.pending = []

    def _check_path(self,path):
        if self.root is not None:
            path = os.path.normpath(os.path.join(self.root,path))
            if len(self.root) == 2 and sys.platform == "win32":
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
            really_rename(target,target_old)
            try:
                really_rename(source,target)
            except:
                really_rename(target_old,target)
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
                really_rename(target,target_old)
            elif os.path.isfile(target) and os.path.isdir(source):
                target_old = target + ".old"
                while os.path.exists(target_old):
                    target_old = target_old + ".old"
                really_rename(target,target_old)
            self._create_parents(target)
            really_rename(source,target)
            if target_old is not None:
                self._remove(target_old)

    def _create_parents(self,target):
        parents = [target]
        while not os.path.exists(os.path.dirname(parents[-1])):
            parents.append(os.path.dirname(parents[-1]))
        for parent in reversed(parents[1:]):
            os.mkdir(parent)

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
                        self.remove(os.path.join(target,nm))
            else:
                self.pending.append(("_copy",source,target))
        else:
            if os.path.isdir(target) or files_differ(source,target):
                self.pending.append(("_copy",source,target))

    def _copy(self,source,target):
        is_win32 = (sys.platform == "win32")
        if is_win32 and os.path.exists(target) and target != source:
            target_old = get_backup_filename(target)
            really_rename(target,target_old)
            try:
                self._do_copy(source,target)
            except:
                really_rename(target_old,target)
                raise
            else:
                try:
                    os.unlink(target_old)
                except EnvironmentError:
                    pass
        else:
            target_old = None
            if os.path.isdir(target) and os.path.isfile(source):
                target_old = get_backup_filename(target)
                really_rename(target,target_old)
            elif os.path.isfile(target) and os.path.isdir(source):
                target_old = get_backup_filename(target)
                really_rename(target,target_old)
            self._do_copy(source,target)
            if target_old is not None:
                self._remove(target_old)

    def _do_copy(self,source,target):
        self._create_parents(target)
        if os.path.isfile(source):
            shutil.copy2(source,target)
        else:
            shutil.copytree(source,target)

    def remove(self,target):
        target = self._check_path(target)
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



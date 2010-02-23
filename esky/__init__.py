#  Copyright (c) 2009, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky:  keep frozen apps fresh

Esky is an auto-update framework for frozen Python applications.  It provides
a simple API through which apps can find, fetch and install updates, and a
bootstrapping mechanism that keeps the app safe in the face of failed or
partial updates.

Esky is currently capable of freezing apps with bbfreeze, cxfreeze and py2exe.
Adding support for other freezer programs should be straightforward; patches
will be gratefully accepted.

The main interface is the 'Esky' class, which represents a frozen app.  An Esky
must be given the path to the top-level directory of the frozen app, and a
'VersionFinder' object that it will use to search for updates.  Typical usage
for an app automatically updating itself would look something like this:

    if hasattr(sys,"frozen"):
        app = esky.Esky(sys.executable,"http://example.com/downloads/")
        app.auto_update()
        app.cleanup()

A simple default VersionFinder is provided that hits a specified URL to get
a list of available versions.  More sophisticated implementations will likely
be added in the future, and you're encouraged to develop a custom VersionFinder
subclass to meet your specific needs.

To freeze your application in a format suitable for use with esky, use the
"bdist_esky" distutils command.  See the docstring of esky.bdist_esky for
full details; the following is an example of a simple setup.py using esky:

    from esky import bdist_esky
    from distutils.core import setup

    setup(name="appname",
          version="1.2.3",
          scripts=["appname/script1.py","appname/gui/script2.pyw"],
          options={"bdist_esky":{"includes":["mylib"]}},
         )

Invoking this setup script would create an esky for "appname" version 1.2.3:

    #>  python setup.py bdist_esky
    ...
    ...
    #>  ls dist/
    appname-1.2.3.linux-i686.zip
    #>

The contents of this zipfile can be extracted to the filesystem to give a
fully working application.  If made available online then it can also be found,
downloaded and used as an upgrade by older versions of the application.

The on-disk layout of an app managed by esky looks like this:

    prog.exe                 - esky bootstrapping executable
    updates/                 - work area for fetching/unpacking updates
    appname-X.Y.platform/    - specific version of the application
        prog.exe             - executable(s) as produced by freezer module
        library.zip          - pure-python frozen modules
        pythonXY.dll         - python DLL
        esky-bootstrap.txt   - list of files expected in the bootstrapping env
        ...other deps...

This is also the layout of the zipfiles produced by bdist_esky.  The 
"appname-X.Y" directory is simply a frozen app directory with some extra
bootstrapping information in the file "esky-bootstrap.txt".

To upgrade to a new version "appname-X.Z", esky performs the following steps:
    * extract it into a temporary directory under "updates"
    * move all bootstrapping files into "appname-X.Z.platm/esky-bootstrap"
    * atomically rename it into the main directory as "appname-X.Z.platform"
    * move contents of "appname-X.Z.platform/esky-bootstrap" into the main dir
    * remove the "appname-X.Z.platform/esky-bootstrap" directory
    * remove files not in "appname-X.Z.platform/esky-bootstrap.txt"
    * remove the "appname-X.Y.platform" directory

Where such facilities are provided by the operating system, this process is
performed within a filesystem transaction. Nevertheless, the esky bootstrapping
executable is able to detect and recover from a failed update should such an
unfortunate situation arise.

To clean up after failed or partial updates, applications should periodically
call the "cleanup" method on their esky.

"""

from __future__ import with_statement

__ver_major__ = 0
__ver_minor__ = 4
__ver_patch__ = 0
__ver_sub__ = ""
__version__ = "%d.%d.%d%s" % (__ver_major__,__ver_minor__,__ver_patch__,__ver_sub__)


import sys
import os
import shutil
import errno
import socket
import time

try:
    import threading
except ImportError:
    threading = None
            

from esky.errors import *
from esky.fstransact import FSTransaction
from esky.finder import DefaultVersionFinder
from esky.util import is_core_dependency, split_app_version, join_app_version,\
                      parse_version, get_best_version


class Esky(object):
    """Class representing an updatable frozen app.

    Instances of this class point to a directory containing a frozen app in
    the esky format.  Through such an instance the app can be updated to a
    new version in-place.  Typical use of this class might be:

        if hasattr(sys,"frozen"):
            app = esky.Esky(sys.executable,"http://example.com/downloads/")
            app.auto_update()
            app.cleanup()

    The first argument must be either the top-level application directory,
    or the path of an executable from that application.  The second argument
    is a VersionFinder object that will be used to search for updates.  If
    a string it passed, it is assumed to be a URL and is passed to a new 
    DefaultVersionFinder instance.
    """

    lock_timeout = 60*60  # 1 hour

    def __init__(self,appdir,version_finder=None):
        if os.path.isfile(appdir):
            appdir = os.path.dirname(os.path.dirname(appdir))
        self.appdir = appdir
        self.reinitialize()
        self._lock_count = 0
        self.version_finder = version_finder

    def _get_version_finder(self):
        return self.__version_finder
    def _set_version_finder(self,version_finder):
        workdir = os.path.join(self.appdir,"updates")
        if version_finder is not None:
            if isinstance(version_finder,basestring):
               kwds = {"download_url":version_finder}
               version_finder = DefaultVersionFinder(**kwds)
        self.__version_finder = version_finder
    version_finder = property(_get_version_finder,_set_version_finder)

    def _get_update_dir(self):
        """Get the directory path in which self.version_finder can work."""
        return os.path.join(self.appdir,"updates")

    def reinitialize(self):
        """Reinitialize internal state by poking around in the app directory.

        If the app directory is found to be in an inconsistent state, a
        EskyBrokenError will be raised.  This should never happen unless
        another process has been messing with the files.
        """
        best_version = get_best_version(self.appdir)
        if best_version is None:
            raise EskyBrokenError("no frozen versions found")
        self.name,self.version,self.platform = split_app_version(best_version)

    def lock(self,num_retries=0):
        """Lock the application directory for exclusive write access.

        If the appdir is already locked by another process/thread then
        EskyLockedError is raised.  There is no way to perform a blocking
        lock on an appdir.

        Locking is achieved by creating a "locked" directory and writing the
        current process/thread ID into it.  os.mkdir is atomic on all platforms
        that we care about. 
        """
        if num_retries > 5:
            raise EskyLockedError
        if threading:
           curthread = threading.currentThread()
           try:
               threadid = curthread.ident
           except AttributeError:
               threadid = curthread.getName()
        else:
           threadid = "0"
        myid = "%s-%s-%s" % (socket.gethostname(),os.getpid(),threadid)
        lockdir = os.path.join(self.appdir,"locked")
        #  Do I already own the lock?
        if os.path.exists(os.path.join(lockdir,myid)):
            #  Update file mtime to keep it safe from breakers
            open(os.path.join(lockdir,myid),"wb").close()
            self._lock_count += 1
            return True
        #  Try to make the "locked" directory.
        try:
            os.mkdir(lockdir)
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise
            #  Is it stale?  If so, break it and try again.
            try:
                newest_mtime = os.path.getmtime(lockdir)
                for nm in os.listdir(lockdir):
                    mtime = os.path.getmtime(os.path.join(lockdir,nm))
                    if mtime > newest_mtime:
                        newest_mtime = mtime
                if newest_mtime + self.lock_timeout < time.time():
                    shutil.rmtree(lockdir)
                    return self.lock(num_retries+1)
                else:
                    raise EskyLockedError
            except OSError, e:
                if e.errno not in (errno.ENOENT,errno.ENOTDIR,):
                    raise
                return self.lock(num_retries+1)
        else:
            #  Success!  Record my ownership
            open(os.path.join(lockdir,myid),"wb").close()
            self._lock_count = 1
            return True
            
    def unlock(self):
        """Unlock the application directory for exclusive write access."""
        self._lock_count -= 1
        if self._lock_count == 0:
            if threading:
               curthread = threading.currentThread()
               try:
                   threadid = curthread.ident
               except AttributeError:
                   threadid = curthread.getName()
            else:
              threadid = "0"
            myid = "%s-%s-%s" % (socket.gethostname(),os.getpid(),threadid)
            lockdir = os.path.join(self.appdir,"locked")
            os.unlink(os.path.join(lockdir,myid))
            os.rmdir(lockdir)

    def cleanup(self):
        """Perform cleanup tasks in the app directory.

        This includes removing older versions of the app and completing any
        failed update attempts.  Such maintenance is not done automatically
        since it can take a non-negligible amount of time.
        """
        appdir = self.appdir
        self.lock()
        try:
            cur_version = get_best_version(appdir)
            new_version = get_best_version(appdir,include_partial_installs=True)
            #  If there's a partial install we must complete it, since it
            #  could have left exes in the bootstrap env and we don't want
            #  to accidentally delete their dependencies.
            if cur_version != new_version:
                (_,v,_) = split_app_version(new_version)
                self.install_version(v)
                cur_version = new_version
            #  Now we can safely remove anything that's not part of the
            #  current version's bootstrap env.
            manifest = self._version_manifest(cur_version)
            for nm in os.listdir(appdir):
                fullnm = os.path.join(appdir,nm)
                if os.path.isdir(fullnm):
                    if nm not in ("updates","locked",cur_version):
                        if nm not in manifest:
                            self._try_remove(fullnm)
                else:
                    if nm not in manifest:
                        self._try_remove(fullnm)
            if self.version_finder is not None:
                self.version_finder.cleanup(self)
        finally:
            self.unlock()

    def _try_remove(self,path):
        """Try to remove the file/directory at the given path.

        This method attempts to remove the file or directory at the given path,
        but will fail silently under a number of conditions:

            * if a file is locked or permission is denied
            * if a directory cannot be emptied of all contents
            * if the path appears on sys.path

        """
        if path not in sys.path:
            try:
                if os.path.isdir(path):
                    for nm in os.listdir(path):
                        self._try_remove(os.path.join(path,nm))
                    os.rmdir(path)
                else:
                    os.unlink(path)
            except EnvironmentError, e:
                if e.errno not in self._errors_to_ignore:
                    raise
    _errors_to_ignore = (errno.ENOENT, errno.EPERM, errno.EACCES, errno.ENOTDIR,
                         errno.EISDIR, errno.EINVAL, errno.ENOTEMPTY,)

    def auto_update(self):
        """Automatically install the latest version of the app."""
        if self.version_finder is None:
            raise NoVersionFinderError
        version = self.find_update()
        if version is not None:
            if parse_version(version) > parse_version(self.version):
                self.fetch_version(version)
                self.install_version(version)
                self.uninstall_version(self.version)
                self.reinitialize()

    def find_update(self):
        """Check for an available update to this app.

        This method returns either None, or a string giving the version of
        the newest available update.
        """
        if self.version_finder is None:
            raise NoVersionFinderError
        best_version = None
        best_version_p = parse_version(self.version)
        for version in self.version_finder.find_versions(self):
            version_p = parse_version(version)
            if version_p > best_version_p:
                best_version_p = version_p
                best_version = version
        return best_version

    def fetch_version(self,version):
        """Fetch the specified updated version of the app."""
        if self.version_finder is None:
            raise NoVersionFinderError
        if not self.version_finder.has_version(self,version):
            self.version_finder.fetch_version(self,version)

    def install_version(self,version):
        """Install the specified version of the app.

        This fetches the specified version if necessary, then makes it
        available as a version directory inside the app directory.  It 
        does not modify any other installed versions.
        """
        #  Extract update then rename into position in main app directory
        target = join_app_version(self.name,version,self.platform)
        target = os.path.join(self.appdir,target)
        if not os.path.exists(target):
            source = self.version_finder.fetch_version(self,version)
        self.lock()
        try:
            if not os.path.exists(target):
                os.rename(source,target)
            trn = FSTransaction()
            try:
                #  Move new bootrapping environment into main app dir.
                #  Be sure to move dependencies before executables.
                bootstrap = os.path.join(target,"esky-bootstrap")
                if os.path.exists(os.path.join(bootstrap,"library.zip")):
                    trn.move(os.path.join(bootstrap,"library.zip"),
                             os.path.join(self.appdir,"library.zip"))
                for nm in os.listdir(bootstrap):
                    if is_core_dependency(nm):
                        trn.move(os.path.join(bootstrap,nm),
                                 os.path.join(self.appdir,nm))
                for nm in os.listdir(bootstrap):
                    if not is_core_dependency(nm) and nm != "library.zip":
                        trn.move(os.path.join(bootstrap,nm),
                                 os.path.join(self.appdir,nm))
                #  Remove the bootstrap dir; the new version is now installed
                trn.remove(bootstrap)
            except Exception:
                trn.abort()
                raise
            else:
                trn.commit()
        finally:
            self.unlock()

    def uninstall_version(self,version): 
        """Uninstall the specified version of the app."""
        target_name = join_app_version(self.name,version,self.platform)
        target = os.path.join(self.appdir,target_name)
        self.lock()
        try:
            if not os.path.exists(target):
                return
            trn = FSTransaction()
            try:
                #  Get set of all files that must stay in the main appdir
                to_keep = set()
                for vname in os.listdir(self.appdir):
                    if vname != target_name:
                        to_keep.update(self._version_manifest(vname))
                #  Remove files used only by the version being removed
                to_rem = self._version_manifest(target_name) - to_keep
                for nm in to_rem:
                    fullnm = os.path.join(self.appdir,nm)
                    trn.remove(fullnm)
                #  Remove/disable the version.
                #  To avoid trying to remove in-use files, we just clobber
                #  the esky-bootstrap.txt file and leave the rest to cleanup().
                trn.remove(os.path.join(target,"esky-bootstrap.txt"))
            except Exception:
                trn.abort()
                raise
            else:
                trn.commit()
        finally:
            self.unlock()

    def _version_manifest(self,vdir):
        """Get the bootstrap manifest for the given version directory.

        This is the set of files/directories that the given version expects
        to be in the main app directory
        """
        mpath = os.path.join(self.appdir,vdir,"esky-bootstrap.txt")
        try:
            with open(mpath,"rt") as mf:
                return set(ln.strip() for ln in mf)
        except IOError:
            return set()


#  Copyright (c) 2009, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky:  keep frozen apps fresh

Esky is an auto-update framework for frozen Python applications.  It provides
a simple API through which apps can find, fetch and install updates, and a
bootstrapping mechanism that keeps the app safe in the face of failed or
partial updates.

Esky is currently capable of freezing apps with bbfreeze or py2exe. Adding
support for other freezer programs should be straightforward; patches will be
gratefully accepted.

The main interface is the 'Esky' class, which represents a frozen app.  An Esky
must be given the path to the top-level directory of the frozen app, and a
'VersionFinder' object that it will use to search for updates.  Typical usage
for an app automatically updating itself would look something like this:

    if hasattr(sys,"frozen"):
        app = esky.Esky(sys.executable,"http://example.com/downloads/")
        new_version = app.find_update()
        if new_version is not None:
            app.install_update(new_version)

A simple default VersionFinder is provided that hits a specified URL to get
a list of available versions.  More sophisticated implementations will likely
be added in the future, and you're encouraged to develop a custom VersionFinder
subclass to meet your specific needs.

When properly installed, the on-disk layout of an app managed by esky looks
like this:

    prog.exe                 - esky bootstrapping executable
    updates/                 - work area for fetching/unpacking updates
    appname-X.Y.platform/    - specific version of the application
        prog.exe             - executable(s) as produced by freezer module
        library.zip          - pure-python frozen modules
        pythonXY.dll         - python DLL
        esky-bootstrap.txt   - list of files expected in the bootstrapping env
        ...other deps...

The "appname-X.Y" directory is simply a frozen app directory with some extra
bootstrapping information produced by esky.  To freeze your app in such a
format, there is a "bdist_esky" command that can be used with a standard
distutils setup.py file; see the docstring for esky.bdist_esky for details.

To upgrade to a new version "appname-X.Z", esky performs the following steps:
    * extract it into a temporary directory under "updates"
    * move all bootstrapping files into "appname-X.Z.platm/esky-bootstrap"
    * atomically rename it into the main directory as "appname-X.Z.platform"
    * move contents of "appname-X.Z.platform/esky-bootstrap" into the main dir
    * remove the "appname-X.Z.platform/esky-bootstrap" directory
    * remove files not in "appname-X.Z.platform/esky-bootstrap.txt"
    * remove the "appname-X.Y.platform" directory

Where such facilities are provided by the operating system, this process is
performed within a filesystem transaction.  Neverthless, the esky bootstrapping
executable is able to detect and recover from a failed update should such an
unfortunate situation arise.

To clean up after failed or partial updates, applications should periodically
call the "cleanup" method on their esky.

"""

__ver_major__ = 0
__ver_minor__ = 3
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
from esky.finder import SimpleVersionFinder
from esky.util import is_core_dependency, split_app_version, join_app_version,\
                      parse_version, get_best_version


class Esky(object):
    """Class representing an updatable frozen app.

    Instances of this class point to a directory containing a frozen app in
    the esky format.  Through such an instance the app can be updated to a
    new version in-place.  Typical use of this class might be:

        if hasattr(sys,"frozen"):
            app = esky.Esky(sys.executable,"http://example.com/downloads/")
            new_version = app.find_update()
            if new_version is not None:
                app.install_update(new_version)

    The first argument must be either the top-level application directory,
    or the path of an executable from that application.  The second argument
    is a VersionFinder object that will be used to search for updates.  If
    a string it passed, it is assumed to be a URL and is passed to a new 
    SimpleVersionFinder instance.
    """

    lock_timeout = 60*60  # 1 hour

    def __init__(self,appdir,version_finder):
        if os.path.isfile(appdir):
            appdir = os.path.dirname(os.path.dirname(appdir))
        self.appdir = appdir
        self.reinitialize()
        self._lock_count = 0
        workdir = os.path.join(appdir,"updates")
        if isinstance(version_finder,basestring):
            version_finder = SimpleVersionFinder(download_url=version_finder)
        version_finder.appname = self.name
        version_finder.platform = self.platform
        version_finder.workdir = workdir
        self.version_finder = version_finder

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
               threadid = str(threading.currentThread().ident)
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
                self.install_update(v)
                cur_version = new_version
            #  Now we can safely remove anything that's not part of the
            #  current version's bootstrap env.
            manifest = os.path.join(appdir,cur_version,"esky-bootstrap.txt")
            manifest = [ln.strip() for ln in open(manifest,"rt")]
            for nm in os.listdir(appdir):
                fullnm = os.path.join(appdir,nm)
                if os.path.isdir(fullnm):
                    if nm not in ("updates","locked",cur_version):
                        if nm not in manifest:
                            shutil.rmtree(fullnm)
                else:
                    if nm not in manifest:
                        os.unlink(fullnm)
            self.version_finder.cleanup()
        finally:
            self.unlock()

    def find_update(self):
        """Check for an available update to this app.

        This method returns either None, or a string giving the version of
        the newest available update.
        """
        best_version = None
        best_version_p = parse_version(self.version)
        for version in self.version_finder.find_versions():
            version_p = parse_version(version)
            if version_p > best_version_p:
                best_version_p = version_p
                best_version = version
        return best_version

    def fetch_update(self,version):
        """Fetch the specified updated version of the app."""
        return self.version_finder.fetch_version(version)

    def install_update(self,version):
        """Install the specified updated version of the app.

        If the specified version is not available locally, it will be fetched
        before proceeding.
        """
        #  Extract update then rename into position in main app directory
        target = join_app_version(self.name,version,self.platform)
        target = os.path.join(self.appdir,target)
        if not os.path.exists(target):
            if not self.version_finder.has_version(version):
                self.version_finder.fetch_version(version)
            source = self.version_finder.prepare_version(version)
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
                #  Remove the bootstrap dir; the new version is now active
                trn.remove(bootstrap)
                #  Remove anything that doesn't belong in the main app dir
                manifest = os.path.join(target,"esky-bootstrap.txt")
                manifest = [ln.strip() for ln in open(manifest,"rt")]
                for nm in os.listdir(self.appdir):
                    fullnm = os.path.join(self.appdir,nm)
                    if nm not in manifest and not os.path.isdir(fullnm):
                        trn.remove(fullnm)
                #  Remove/disable the old version.
                #  On win32 we can't remove in-use files, so just clobber
                #  library.zip and leave to rest to a cleanup() call.
                oldv = join_app_version(self.name,self.version,self.platform)
                oldv = os.path.join(self.appdir,oldv)
                if sys.platform == "win32":
                    trn.remove(os.path.join(oldv,"library.zip"))
                else:
                    for (dirp,dirnms,filenms) in os.walk(oldv,topdown=False):
                        for fn in filenms:
                            trn.remove(os.path.join(dirp,fn))
                        for dn in dirnms:
                            trn.remove(os.path.join(dirp,dn))
                    trn.remove(oldv)
            except Exception:
                trn.abort()
                raise
            else:
                trn.commit()
        finally:
            self.unlock()
        self.reinitialize()



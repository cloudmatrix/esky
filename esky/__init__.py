"""

  esky:  keep frozen apps fresh

Esky is an auto-update framework for frozen Python applications, built on top 
of bbfreeze.  It provides a simple API through which apps can find, fetch
and install updates, and a bootstrapping mechanism that keeps the app safe
in the face of failed or partial updates.

The main interface is the 'Esky' class, which represents a frozen app.  An Esky
must be given the top-level directory of the frozen application, and it can
then be used to find and install updates to that application.  Typical usage
for an app automatically updating itself would look something like this:

    if sys.frozen:
        app = esky.Esky(sys.executable,"http://example.com/downloads/")
        new_version = app.find_update()
        if new_version is not None:
            app.install_update(new_version)

The work of finding and fectching new versions is handled by a "VersionFinder"
object.  A simple default VersionFinder is provided that hits a specified URL
to get a list of available versions.  More sophisticated implementations will
be added in the future, and you're encouraged to develop a custom VersionFinder
subclass to meet your specific needs.

When properly installed, the on-disk layout of an app managed by esky looks
like this:

    prog.exe                 - esky bootstrapping executable
    updates/                 - work area for fecthing/unpacking updates
    appname-X.Y/             - specific version of the application
        prog.exe             - executable(s) as produced by bbfreeze
        library.zip          - pure-python modules frozen by bbfreeze
        pythonXY.dll         - python DLL
        esky-bootstrap/      - updated esky bootstrapping environment
        esky-bootstrap.txt   - list of files in the updated bootstrapping env
        frozen.txt           - list of frozen executables
        ...other deps...

The "appname-X.Y" directory is simply a bbfrozen app directory with an extra
metadata file - 'frozen.txt' contains a listing of the frozen executables.
At application startup, esky takes care of detecting the "appname-X.Y"
directory and bootstrapping into it.  Moreover, any failed or partial updates
are detected and either completed or rolled back.

To freeze your app in a format suitable for esky, there is a "bdist_esky"
command that can be used with a standard distutils setup.py file.

To install an updated version, esky performs the following steps:
    * extract it into a temporary directory under "updates"
    * atomically rename it into the main directory as "appname-X.Z"
    * move the contents of the esky-bootstrap directory into the app dir
    * delete the esky-bootstrap directory
    * remove anything in the app dir that isn't listed in esky-bootstrap.txt
    * remove the old "appname-X.Y" directory

"""

__ver_major__ = 0
__ver_minor__ = 1
__ver_patch__ = 0
__ver_sub__ = ""
__version__ = "%d.%d.%d%s" % (__ver_major__,__ver_minor__,
                              __ver_patch__,__ver_sub__)


import sys
import os
import shutil
import errno

from esky.errors import *
from esky.bootstrap import split_app_version, parse_version, get_best_version
from esky.fstransact import FSTransaction
from esky.finder import SimpleVersionFinder


class Esky(object):
    """Class representing an updatable frozen app.

    Instances of this class point to a directory containing a frozen app in
    the esky format.  Through such an instance the app can be updated to a
    new version in-place.  Typical use of this class might be:

        if sys.frozen:
            app = esky.Esky(sys.executable,"http://example.com/downloads/")
            new_version = app.find_update()
            if new_version is not None:
                app.install_update(new_version)

    """

    def __init__(self,appdir,version_finder):
        if os.path.isfile(appdir):
            appdir = os.path.dirname(os.path.dirname(appdir))
        self.appdir = appdir
        self.reinitialize()
        workdir = os.path.join(appdir,"updates")
        if isinstance(version_finder,basestring):
            self.version_finder = SimpleVersionFinder(appname=self.name,workdir=workdir,download_url=version_finder)
        else:
            self.version_finder = version_finder
            self.version_finder.appname = self.name
            self.version_finder.workdir = workdir

    def reinitialize(self):
        """Reinitialize internal state by poking around in the app directory.

        If the app directory is found to be in an inconsistent state, a
        BrokenEskyError will be raised.  This should never happen unless
        another process has been messing with the files.
        """
        best_version = get_best_version(self.appdir)
        if best_version is None:
            raise BrokenEskyError("no frozen versions found")
        self.name,self.version = split_app_version(best_version)

    def cleanup(self):
        """Perform cleanup tasks in the app directory.

        This includes removing older versions of the app and failed update
        attempts.  Such maintenance is not done automatically since it can
        take a non-negligible amount of time.
        """
        version = get_best_version(self.appdir)
        manifest = os.path.join(self.appdir,version,"esky-bootstrap.txt")
        manifest = [ln.strip() for ln in open(manifest,"rt")]
        for nm in os.listdir(self.appdir):
            fullnm = os.path.join(self.appdir,nm)
            if os.path.isdir(fullnm):
                if nm != "updates" and nm != version:
                    shutil.rmtree(fullnm)
            else:
                if nm not in manifest:
                    os.unlink(fullnm)
        self.version_finder.cleanup()

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

        If the specified version is not available locally, this will call
        fetch_update() to obtain it.
        """
        #  Extract update then rename into position in main app directory
        target = os.path.join(self.appdir,"%s-%s"%(self.name,version))
        if not os.path.exists(target):
            if not self.version_finder.has_version(version):
                self.version_finder.fetch_version(version)
            source = self.version_finder.prepare_version(version)
            os.rename(source,target)
        #  Move files out of the bootstrapping environment, and remove files
        #  that are no longer required.
        trn = FSTransaction()
        try:
            #  Move new bootrapping environment into main app dir
            bootstrap = os.path.join(target,"esky-bootstrap")
            for nm in os.listdir(bootstrap):
                trn.move(os.path.join(bootstrap,nm),
                         os.path.join(self.appdir,nm))
            #  Remove the bootstrap dir - this version is now active
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
            oldv = os.path.join(self.appdir,"%s-%s"%(self.name,self.version,))
            if sys.platform == "win32":
                trn.remove(os.path.join(oldv,"library.zip"))
            else:
                for (dirpath,dirnames,filenames) in os.walk(oldv,topdown=False):
                    for fn in filenames:
                        trn.remove(os.path.join(dirpath,fn))
                    for dn in dirnames:
                        trn.remove(os.path.join(dirpath,dn))
                trn.remove(oldv)
        except Exception:
            trn.abort()
            raise
        else:
            trn.commit()
        self.reinitialize()



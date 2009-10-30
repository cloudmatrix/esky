"""

  esky:  an auto-update system for frozen python apps

This package provides some management infrastructure around apps frozen by
'bbfreeze', allowing them to be automatically updated in-place.  The process
preserves the integrity of the app at all times during the update - it will
never be left in an unrunnable state, even if there's a system crash in the
middle of an update.

The main interface is the 'Esky' class, which represents a frozen app.  An Esky
must be given the top-level directory of the frozen application, and it has the
following useful methods:

    * find_update()
    * fetch_update(version)
    * install_update(version)

The default implementation is quite simplistic, hitting a specified URL to
get a list of available versions that can be downloaded as zipfiles or tarfiles.
More sophisticated implementations will be added in the future, and you're
encouraged to override any or all of the above methods to suit your needs.

The on-disk layout of an app managed by esky looks some thing like this:

    prog.exe
    pythonXY.dll
    library.zip
    scratch/
        downloads/
    appname-X.Y.Z/
        library.zip
        depmod.pyd

The contents of the "appname-X.Y.Z" directory are the bbfreeze of a specific
version of the application, while the top-level files serve to bootstrap into
that environment.  Updates are performed by creating the bbfreeze directory
for the new version and then removing the directory for the old version; if
this process fails and leaves behind the old directory, the bootstrap script
is smart enough to use the newer version.

To freeze your app in a format suitable for esky, there is a "bdist_esky"
command that can be used with a standard distutils setup.py file.

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

from esky.errors import *
from esky.bootstrap import split_app_version, parse_version, get_best_version


class Esky(object):
    """Class representing an updatable frozen app.

    Instances of this class point to a directory containing a frozen app in
    the "esky" format.  Through such an instance the app can be updated to
    a new version in-place.
    """

    def __init__(self,app_dir,update_finder):
        self.app_dir = app_dir
        if isinstance(update_finder,basestring):
            self.update_finder = SimpleUpdateFinder(update_finder)
        else:
            self.update_finder = update_finder
        self.reinitialize()

    def reinitialize(self):
        """Reinitialize internal state by poking around in the app directory.

        If the app directory is found to be in an inconsistent state, a
        BrokenEskyError will be raised.  This should never happen unless
        another process has been messing with the files.
        """
        try:
            appver = get_best_version(self.app_dir)
        except RuntimeError, e:
             if e.args and e.args[0] == "no frozen versions found":
                 raise BrokenEskyError("no frozen versions found")
             else:
                 raise
        self.name,self.version = split_app_version(appver)

    def cleanup(self):
        """Perform cleanup tasks in the app directory.

        This includes removing older versions of the app and failed upgrade
        attempts.  Such maintenance is not done automatically since it can
        take a non-negligible amount of time.
        """
        for nm in os.listdir(self.app_dir):
            if nm in ("library.zip","scratch",):
                continue
            fullnm = os.path.join(self.app_dir,nm)
            if os.path.isdir(fullnm):
                (_,ver) = split_app_version(nm)
                if parse_version(ver) < parse_version(self.version):
                    shutil.rmtree(fullnm)
        self.update_finder.cleanup(self)

    def find_update(self):
        """Check for an available update to this app.

        This method returns either None, or a string giving the version of
        the newest available update.
        """
        return self.update_finder.find_update(self)

    def fetch_update(self,version):
        """Fetch the specified updated version of the app."""
        return self.update_finder.fetch_update(self,version)

    def install_update(self,version):
        """Install the specified updated version of the app.

        If the specified version is not available locally, this will call
        fetch_update() to obtain it.
        """
        if not self.update_finder.has_update(version):
            self.update_finder.fetch_update(version)


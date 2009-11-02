"""

  esky:  keep frozen apps fresh

Esky is an auto-update framework for frozen Python applications, built on top 
of bbfreeze.  It provides a simple API through which apps can find, fetch
and install updates, and a bootstrapping mechanism that keeps the app safe
in the face of failed or partial upgrades.

The main interface is the 'Esky' class, which represents a frozen app.  An Esky
must be given the top-level directory of the frozen application, and it can
then be used to find and install updates to that application.  Typical usage
for an app automatically updating itself would look something like this:

    if sys.frozen:
        app = esky.Esky(os.path.dirname(sys.executable))
        new_version = app.find_update()
        if new_version is not None:
            app.install_update(new_version)

The work of finding and fectching new versions is handled by an "UpdateFinder"
object.  A simple default UpdateFinder is provided that hits a specified URL
to get a list of available options.  More sophisticated implementations will
be added in the future, and you're encouraged to develop a custom UpdateFinder
subclass to meet your specific needs.

The frozen contents for a specific version of an esky app must look something
like this:

    prog.exe                   - executable(s) as produced by bbfreeze
    library.zip                - pure-python modules frozen by bbfreeze
    pythonXY.dll               - python DLL
    esky-info.txt              - meta-data about the frozen app
    bootstrap-library.zip      - esky bootstrapping library
    ...other deps...

This is simply a bbfrozen app directory with some additional data.  The file
'esky-info.txt' contains information about the frozen application - the first
line is the python version tuple, and the second line is a list of the
executables included in the freeze.

To freeze your app in a format suitable for esky, there is a "bdist_esky"
command that can be used with a standard distutils setup.py file.

When properly installed, the on-disk layout of an app managed by esky looks
like this:

    prog.exe                   - executable(s) as produced by bbfreeze
    library.zip                - esky bootstrapping library
    pythonXY.dll               - python DLL
    updates/                   - work area for fecthing/unpacking updates
    appname-X.Y/             - specific version of the application
        library.zip            - pure-python modules frozen by bbfreeze
        ...other deps...

At application startup, esky takes care of detecting the "appname-X.Y"
directory and bootstrapping into it.  Moreover, any failed or partial updates
are detected and either completed or rolled back.

To install an updated version, esky performs the following steps:
    * extract it into a temporary directory under "updates"
    * atomically rename it into the main directory as "appname-X.Z"
    * atomically rename "appname-X.Z/bootstrap-library.zip" to "library.zip"
    * atomically rename each frozen executable into the main directory
    * remove "appname-X.Y/library.zip"
    * remove the remaining "appname-X.Y" directory

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
    the esky format.  Through such an instance the app can be updated to a
    new version in-place.  Typical use of this class might be:

        if sys.frozen:
            app = esky.Esky(os.path.dirname(sys.executable))
            new_version = app.find_update()
            if new_version is not None:
                app.install_update(new_version)

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


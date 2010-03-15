

  esky:  keep frozen apps fresh

Esky is an auto-update framework for frozen Python applications.  It provides
a simple API through which apps can find, fetch and install updates, and a
bootstrapping mechanism that keeps the app safe in the face of failed or
partial updates.

Esky is currently capable of freezing apps with bbfreeze, cxfreeze py2exe and
py2app. Adding support for other freezer programs should be straightforward;
patches will be gratefully accepted.

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


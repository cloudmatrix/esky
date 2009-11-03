

  esky:  keep frozen apps fresh

Esky is an auto-update framework for frozen Python applications, built on top 
of bbfreeze.  It provides a simple API through which apps can find, fetch
and install updates, and a bootstrapping mechanism that keeps the app safe
in the face of failed or partial updates.

The main interface is the 'Esky' class, which represents a frozen app.  An Esky
must be given the path to the top-level directory of the frozen app, and a
"VersionFinder" object that it will use to search for updates.  Typical usage
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
    appname-X.Y/             - specific version of the application
        prog.exe             - executable(s) as produced by bbfreeze
        library.zip          - pure-python modules frozen by bbfreeze
        pythonXY.dll         - python DLL
        esky-bootstrap/      - updated esky bootstrapping environment
        esky-bootstrap.txt   - list of files in the updated bootstrapping env
        ...other deps...

The "appname-X.Y" directory is simply a bbfrozen app directory with some extra
bootstrapping information produced by esky.  To freeze your app in such a
format, there is a "bdist_esky" command that can be used with a standard
distutils setup.py file.

To upgrade to a new version "appname-X.Z", esky performs the following steps:
    * extract it into a temporary directory under "updates"
    * atomically rename it into the main directory as "appname-X.Z"
    * move the contents of "appname-X.Z/esky-bootstrap" into the main dir
    * remove the "appname-X.Z/esky-bootstrap" directory
    * remove files not in "appname-X.Z/esky-bootstrap.txt" from the main dir
    * remove the "appname-X.Y" directory

Where such facilities are provided by the operating system, this process is
performed within a filesystem transaction.  Neverthless, the esky bootstrapping
executable is able to detect and recover from a failed update should such an
unfortunate situation arise.

To clean up after failed or partial updates, applications should periodically
call the "cleanup" method on their esky.


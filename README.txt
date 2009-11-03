

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


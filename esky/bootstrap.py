"""

  esky.bootstrap:  minimal bootstrapping code for esky

This module provides the minimal code necessary to bootstrap a frozen
application packaged using esky.  It checks the runtime directory to find
the most appropriate version of the app and chain-loads the standard bbfreeze
bootstrapper.

The code from this module becomes the __main__ module in the bootstrapping
environment created by esky.  At application load time, it is executed with
module name "__builtin__".

"""

def bootstrap():
    import sys
    #  bbfreeze always sets sys.path to [appdir/library.zip,appdir]
    appdir = sys.path[1]
    del sys.path[:]
    #  The os module hasn't been bootstrapped yet, so we grab what
    #  we can directly from builtins and fudge the rest.
    if "posix" in sys.builtin_module_names:
        from posix import listdir, stat
        sep = "/"
    elif "nt" in  sys.builtin_module_names:
        from nt import listdir, stat
        sep = "\\"
    else:
        raise RuntimeError("unsupported platform: " + sys.platform)
    #  Find the best available version and bootstrap its environment
    for nm in listdir(appdir):
        vdir = appdir + sep + nm
        vlib = appdir + sep + "library.zip"
        try:
            stat(vlib)
        except OSError:
            pass
        else:
            sys.path.append(vlib)
            sys.path.append(vdir)
            break
    else:
        raise RuntimeError("no frozen versions found")
    #  Now chain-load the original bbfreeze __main__ module
    import zipimport
    importer = zipimport.zipimporter(sys.path[0])
    exec importer.get_code("__main__") in {}


if __name__ == "__builtin__":
    bootstrap()


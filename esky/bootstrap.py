
import sys

def bootstrap():
    distdir = sys.path[1]
    del sys.path[:]
    #  The os module hasn't been bootstrapped yet, so we grab what
    #  we can directly from builtins and fudge the rest.
    _names = sys.builtin_module_names
    if "posix" in _names:
        from posix import listdir, stat
        sep = "/"
    elif "nt" in _names:
        from nt import listdir, stat
        sep = "\\"
    else:
        raise RuntimeError("unsupported platform: " + sys.platform)
    #  Find the best available version and bootstrap its environment
    for nm in listdir(distdir):
        libdir = distdir + sep + nm
        libfile = libdir + sep + "library.zip"
        try:
            stat(libfile)
        except OSError:
            pass
        else:
            sys.path.append(libfile)
            sys.path.append(libdir)
            break
    else:
        raise RuntimeError("no frozen versions found")
    #  Now chain-load the original bbfreeze __main__ module
    import zipimport
    importer = zipimport.zipimporter(sys.path[0])
    exec importer.get_code("__main__") in {}


if __name__ == "__builtin__":
    bootstrap()


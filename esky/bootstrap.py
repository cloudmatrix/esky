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
    """Bootstrap an esky frozen app into newest available version."""
    #  bbfreeze always sets sys.path to [appdir/library.zip,appdir]
    import sys
    appdir = sys.path[1]
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
    best_version = None
    best_vdir = None
    for nm in listdir(appdir):
        (app,ver) = split_app_version(nm)
        if ver:
            vdir = appdir + sep + nm
            try:
                stat(vdir + sep + "library.zip")
            except OSError:
                pass
            else:
                ver = parse_version(ver)
                if ver > best_version:
                    best_version = ver
                    best_vdir = vdir
    if best_version is None:
        raise RuntimeError("no frozen versions found")
    #  Now chain-load the original bbfreeze __main__ module
    del sys.path[:]
    sys.path.append(best_vdir + sep + "library.zip")
    sys.path.append(best_vdir)
    import zipimport
    importer = zipimport.zipimporter(sys.path[0])
    exec importer.get_code("__main__") in {}


def split_app_version(s):
    """Split a app version string to name and version components.

    For example, appname-0.1.2 => ("appname","0.1.2")
    """
    bits = s.split("-")
    idx = 1
    while idx < len(bits):
        if bits[idx]:
            if not bits[idx][0].isalpha() or not bits[idx].isalnum():
                break
        idx += 1
    return ("-".join(bits[:idx]),"-".join(bits[idx:]))
    

def parse_version(s):
    """Parse a version string into a chronologically-sortable key

    This function returns a tuple of strings that compares with the results
    for other versions in a chronologically sensible way.  You'd use it to
    compare two version strings like so:

        if parse_version("1.9.2") > parse_version("1.10.0"):
            print "what rubbish, that's an older version!"

    This is essentially the parse_version() function from pkg_resources,
    but re-implemented to avoid using modules that may not be available
    during bootstrapping.
    """
    parts = []
    for part in _parse_version_parts(s.lower()):
        if part.startswith('*'):
            if part<'*final':   # remove '-' before a prerelease tag
                while parts and parts[-1]=='*final-': parts.pop()
            # remove trailing zeros from each series of numeric parts
            while parts and parts[-1]=='00000000':
                parts.pop()
        parts.append(part)
    return tuple(parts)


_replace_p = {'pre':'c', 'preview':'c','-':'final-','rc':'c','dev':'@'}.get
def _parse_version_parts(s):
    for part in _split_version_components(s):
        part = _replace_p(part,part)
        if not part or part=='.':
            continue
        if part[:1] in '0123456789':
            yield part.zfill(8)    # pad for numeric comparison
        else:
            yield '*'+part
    yield '*final'  # ensure that alpha/beta/candidate are before final


def _split_version_components(s):
    start = 0
    while start < len(s):
        end = start+1
        if s[start].isdigit():
            while end < len(s) and s[end].isdigit():
                end += 1
        elif s[start].isalpha():
            while end < len(s) and s[end].isalpha():
                end += 1
        elif s[start] in (".","-"):
            pass
        else:
            while end < len(s) and not (s[end].isdigit() or s[end].isalpha() or s[end] in (".","-")):
                end += 1
        yield s[start:end]
        start = end


if __name__ == "__builtin__":
    bootstrap()


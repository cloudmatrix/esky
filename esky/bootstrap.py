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

import sys

#  The os module might not have been bootstrapped yet, so we grab what
#  we can directly from builtin modules and fudge the rest.
if "posix" in sys.builtin_module_names:
    from posix import listdir, stat
    def pathjoin(*args):
        return "/".join(args)
elif "nt" in  sys.builtin_module_names:
    from nt import listdir, stat
    def pathjoin(*args):
        return "\\".join(args)
else:
    raise RuntimeError("unsupported platform: " + sys.platform)


def bootstrap():
    """Bootstrap an esky frozen app into newest available version."""
    #  bbfreeze always sets sys.path to [appdir/library.zip,appdir]
    appdir = sys.path[1]
    best_version = get_best_version(appdir)
    del sys.path[:]
    sys.path.append(pathjoin(appdir,best_version,"library.zip"))
    sys.path.append(pathjoin(appdir,best_version))
    import zipimport
    importer = zipimport.zipimporter(sys.path[0])
    exec importer.get_code("__main__") in {}


def get_best_version(appdir):
    """Get the name of the best version directory in the given appdir."""
    #  Find the best available version and bootstrap its environment
    best_name = None
    best_version = None
    for nm in listdir(appdir):
        (_,ver) = split_app_version(nm)
        if ver:
            try:
                stat(pathjoin(appdir,vdir,"library.zip"))
            except OSError:
                pass
            else:
                ver = parse_version(ver)
                if ver > best_version:
                    best_version = ver
                    best_name = nm
    if best_version is None:
        raise RuntimeError("no frozen versions found")
    return best_name


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
    """Split version string into individual tokens.

    pkg_resources does this using a regexp: (\d+ | [a-z]+ | \.| -)
    Unfortunately the 're' module isn't in the bootstrap, so we have to do
    an equivalent parse by hand.  Forunately, that's pretty easy.
    """
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


#  Copyright (c) 2009, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.bootstrap:  minimal bootstrapping code for esky

This module provides the minimal code necessary to bootstrap a frozen
application packaged using esky.  It checks the runtime directory to find
the most appropriate version of the app and then execvs to the frozen exe.

This module must use no modules other than builtins, since the stdlib is
not available in the bootstrapping environment.  It must also be capable
of bootstrapping into apps made with older versions of esky, since a partial
update could result in the boostrapper from a new version being forced
to load an old version.

The code from this module becomes the __main__ module in the bootstrapping
environment created by esky.  At application load time, it is executed with
module name "__builtin__".

I plan to eventually replace this with a custom loader written in C, but
for now this lets us get up and running with minimal effort.

"""

import sys
import errno

#  The os module is not builtin, so we grab what we can from the
#  platform-specific modules and fudge the rest.
if "posix" in sys.builtin_module_names:
    from posix import listdir, stat, execv, unlink, rename
    def pathjoin(*args):
        """Local re-implementation of os.path.join."""
        return "/".join(args)
    def basename(p):
        """Local re-implementation of os.path.basename."""
        return p.split("/")[-1]
elif "nt" in  sys.builtin_module_names:
    from nt import listdir, stat, spawnv, P_WAIT, unlink, rename
    execv = None
    def pathjoin(*args):
        """Local re-implementation of os.path.join."""
        return "\\".join(args)
    def basename(p):
        """Local re-implementation of os.path.basename."""
        return p.split("\\")[-1]
else:
    raise RuntimeError("unsupported platform: " + sys.platform)


def exists(path):
    """Local re-implementation of os.path.exists."""
    try:
        stat(path)
    except EnvironmentError, e:
        if e.errno not in (errno.ENOENT,errno.ENOTDIR,):
            raise
        else:
            return False
    else:
        return True


def bootstrap():
    """Bootstrap an esky frozen app into newest available version."""
    #  bbfreeze always sets sys.path to [appdir/library.zip,appdir]
    appdir = sys.path[1]
    best_version = get_best_version(appdir)
    if best_version is None:
        raise RuntimeError("no usable frozen versions were found")
    target_exe = pathjoin(appdir,best_version,basename(sys.executable))
    if execv:
        execv(target_exe,[target_exe] + sys.argv[1:])
    else:
        res = spawnv(P_WAIT,target_exe,[target_exe] + sys.argv[1:])
        raise SystemExit(res)


def get_best_version(appdir):
    """Get the best usable version from within the given appdir.

    In the common case there is only a single version directory, but failed
    or partial updates can result in several being present.  This function
    finds the highest-numbered version that is completely installed.
    """
    #  Find all potential version directories, sorted by version number.
    #  To be a version directory, it must contain a "library.zip".
    candidates = []
    for nm in listdir(appdir):
        (_,ver) = split_app_version(nm)
        if ver and exists(pathjoin(appdir,nm,"library.zip")):
            ver = parse_version(ver)
            candidates.append((ver,nm))
    candidates = [c[1] for c in sorted(candidates,reverse=True)]
    #  In the (hopefully) common case of no failed upgrade, we don't need
    #  to poke around in the filesystem so we just return asap.
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    #  If there are several candidate versions, we need to find the best
    #  one whose 'esky-bootstrap' dir has been completely removed.
    while candidates:
        nm = candidates.pop(0)
        if not exists(pathjoin(appdir,nm,"esky-bootstrap")):
            return nm
    return None


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


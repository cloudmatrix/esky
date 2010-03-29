#  Copyright (c) 2009, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.bootstrap:  minimal bootstrapping code for esky

This module provides the minimal code necessary to bootstrap a frozen
application packaged using esky.  It checks the base runtime directory to
find the most appropriate version of the app and then execvs to the frozen
executable.

This module must use no modules other than builtins, since the stdlib is
not available in the bootstrapping environment.  It must also be capable
of bootstrapping into apps made with older versions of esky, since a partial
update could result in the boostrapper from a new version being forced
to load an old version.

The code from this module is always executed in the bootstrapping environment
before any custom bootstrapping code.  It provides the following functions for
use during the bootstrap process:

  Chainloading:         execv, chainload
  Filesystem:           listdir, exists, basename, dirname, pathjoin
  Version handling:     split_app_version, join_app_version, parse_version,
                        get_all_version, get_best_version


"""

import sys
import errno

#  The os module is not builtin, so we grab what we can from the
#  platform-specific modules and fudge the rest.
if "posix" in sys.builtin_module_names:
    from posix import listdir, stat, unlink, rename, execv
    SEP = "/"
    try:
        import fcntl
    except ImportError:
        fcntl = None
elif "nt" in sys.builtin_module_names:
    from nt import listdir, stat, unlink, rename, spawnv, P_WAIT
    SEP = "\\"
    fcntl = None
    def execv(filename,args):
        res = spawnv(P_WAIT,filename,args)
        raise SystemExit(res)
else:
    raise RuntimeError("unsupported platform: " + sys.platform)


def pathjoin(*args):
    """Local re-implementation of os.path.join."""
    return SEP.join(args)

def basename(p):
    """Local re-implementation of os.path.basename."""
    return p.split(SEP)[-1]

def dirname(p):
    """Local re-implementation of os.path.dirname."""
    return SEP.join(p.split(SEP)[:-1])

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

def appdir_from_executable(exepath):
    """Find the top-level application directory, given sys.executable.

    Ordinarily this would simply be the directory containing the executable,
    but when running via a bundle on OSX the executable will be located at
    <appdir>/Contents/MacOS/<exe>.
    """
    appdir = dirname(exepath)
    if sys.platform == "darwin" and basename(appdir) == "MacOS":
        # Looks like we might be in an app bundle.
        appdir = dirname(appdir)
        if basename(appdir) == "Contents":
            # Yep, definitely in a bundle
            appdir = dirname(appdir)
        else:
            # Nope, some other crazy scheme
            appdir = dirname(exepath)
    return appdir


def bootstrap():
    """Bootstrap an esky frozen app into the newest available version.

    This function searches the application directory to find the highest-
    numbered version of the application that is fully installed, then
    chain-loads that version of the application.
    """
    appdir = appdir_from_executable(sys.executable)
    best_version = get_best_version(appdir)
    if best_version is None:
        raise RuntimeError("no usable frozen versions were found")
    return chainload(pathjoin(appdir,best_version))


def chainload(target_dir):
    """Load and execute the selected version of an application.

    This function replaces the currently-running executable with the equivalent
    executable from the given target directory.

    On platforms that support it, this also locks the target directory so that
    it will not be removed by any simultaneously-running instances of the
    application.
    """
    global _version_dir_lockfile
    lockfile = pathjoin(target_dir,"esky-bootstrap.txt")
    try:
        #  On windows, holding the file open is enough to lock it.
        #  On other platforms, try for a shared lock using fcntl.
        #  We put the fileobj in a global to hold it open.
        _version_dir_lockfile = open(lockfile,"r")
        if "nt" not in sys.builtin_module_names:
            if fcntl is not None:
                fd = _version_dir_lockfile.fileno()
                fcntl.lockf(fd,fcntl.LOCK_SH)
    except EnvironmentError:
        #  If the lockfile has gone missing, the version is being uninstalled.
        #  Our only option is to re-execute ourself and find the new version.
        if exists(lockfile):
            raise
        execv(sys.executable,sys.argv)
    else:
        #  If all goes well, we can actually launch the target version.
        _chainload(target_dir)


def _chainload(target_dir):
    """Default implementation of the chainload() function.

    Specific freezer modules may provide a more efficient, reliable or
    otherwise better version of this function.
    """
    appdir = dirname(target_dir)
    target_exe = target_dir + sys.executable[len(appdir):]
    execv(target_exe,[target_exe] + sys.argv[1:])


def get_best_version(appdir,include_partial_installs=False):
    """Get the best usable version directory from inside the given appdir.

    In the common case there is only a single version directory, but failed
    or partial updates can result in several being present.  This function
    finds the highest-numbered version that is completely installed.
    """
    #  Find all potential version directories, sorted by version number.
    candidates = []
    for nm in listdir(appdir):
        (_,ver,_) = split_app_version(nm)
        if ver and is_version_dir(pathjoin(appdir,nm)):
            ver = parse_version(ver)
            candidates.append((ver,nm))
    candidates = [c[1] for c in sorted(candidates,reverse=True)]
    #  In the (hopefully) common case of no failed updates, we don't need
    #  to poke around in the filesystem so we just return asap.
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if include_partial_installs:
        return candidates[0]
    #  If there are several candidate versions, we need to find the best
    #  one that is completely installed.
    while candidates:
        nm = candidates.pop(0)
        if is_installed_version_dir(pathjoin(appdir,nm)):
            return nm
    return None


def get_all_versions(appdir,include_partial_installs=False):
    """Get a list of all usable version directories inside the given appdir.

    The list will be in order from most-recent to least-recent.  The head
    of the list will be the same directory as returned by get_best_version.
    """
    #  Find all potential version directories, sorted by version number.
    candidates = []
    for nm in listdir(appdir):
        (_,ver,_) = split_app_version(nm)
        if ver and is_version_dir(pathjoin(appdir,nm)):
            ver = parse_version(ver)
            candidates.append((ver,nm))
    candidates = [c[1] for c in sorted(candidates,reverse=True)]
    #  Filter out any that are not completely installed.
    if not include_partial_installs:
        i = 0
        while i < len(candidates):
            if not is_installed_version_dir(pathjoin(appdir,candidates[i])):
                del candidates[i]
            else:
                i += 1
    return candidates


def is_version_dir(vdir):
    """Check whether the given directory contains an esky app version.

    Currently, it only need contain the "esky-bootstrap.txt" file.
    """
    return exists(pathjoin(vdir,"esky-bootstrap.txt"))


def is_installed_version_dir(vdir):
    """Check whether the given version directory is fully installed.

    Currently, a completed installation is indicated by the lack of an
    "esky-bootstrap" directory.
    """
    return not exists(pathjoin(vdir,"esky-bootstrap"))


def split_app_version(s):
    """Split an app version string to name, version and platform components.

    For example, app-name-0.1.2.win32 => ("app-name","0.1.2","win32")
    """
    bits = s.split("-")
    idx = 1
    while idx < len(bits):
        if bits[idx]:
            if not bits[idx][0].isalpha() or not bits[idx].isalnum():
                break
        idx += 1
    appname = "-".join(bits[:idx])
    bits = "-".join(bits[idx:]).split(".")
    version = ".".join(bits[:-1])
    platform = bits[-1]
    return (appname,version,platform)


def join_app_version(appname,version,platform):
    """Join an app name, version and platform into a version directory name.

    For example, ("app-name","0.1.2","win32") => appname-0.1.2.win32
    """
    return "%s-%s.%s" % (appname,version,platform,)
    

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


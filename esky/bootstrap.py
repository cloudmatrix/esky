#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
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
                        get_all_versions, get_best_version, is_version_dir,
                        is_installed_version_dir, is_uninstalled_version_dir,
                        lock_version_dir, unlock_version_dir


"""

import sys
import errno

#  The os module is not builtin, so we grab what we can from the
#  platform-specific modules and fudge the rest.
if "posix" in sys.builtin_module_names:
    import fcntl
    from posix import listdir, stat, unlink, rename, execv
    SEP = "/"
elif "nt" in sys.builtin_module_names:
    fcntl = None
    from nt import listdir, stat, unlink, rename, spawnv, P_WAIT
    SEP = "\\"
    #  The standard execv terminates the spawning process, which makes
    #  it impossible to wait for it.  This alternative is waitable, but
    #  risks leaving zombie children if it is killed externally.
    #  TODO: some way to kill children when this is killed - should be doable
    #        with some custom code in child startup.
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
        if e.errno not in (errno.ENOENT,errno.ENOTDIR,errno.ESRCH,):
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
    best_version = None
    if __esky_name__ is not None:
        best_version = get_best_version(appdir,appname=__esky_name__)
    if best_version is None:
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
    try:
        lock_version_dir(target_dir)
    except EnvironmentError:
        #  If the bootstrap file is missing, the version is being uninstalled.
        #  Our only option is to re-execute ourself and find the new version.
        if exists(pathjoin(target_dir,"esky-bootstrap.txt")):
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
    try:
        execv(target_exe,[target_exe] + sys.argv[1:])
    except EnvironmentError, e:
        if e.errno == errno.ENOENT:
            # Tried to chainload something that doesn't exist.
            # Perhaps executing from a backup file?
            orig_exe = get_original_filename(sys.executable)
            if orig_exe is not None:
                target_exe = target+dir + orig_executable[len(appdir):]
                execv(target_exe,[target_exe] + sys.argv[1:])


def get_best_version(appdir,include_partial_installs=False,appname=None):
    """Get the best usable version directory from inside the given appdir.

    In the common case there is only a single version directory, but failed
    or partial updates can result in several being present.  This function
    finds the highest-numbered version that is completely installed.
    """
    #  Find all potential version directories, sorted by version number.
    candidates = []
    for nm in listdir(appdir):
        (appnm,ver,platform) = split_app_version(nm)
        #  If its name didn't parse properly, don't bother looking inside.
        if ver and platform:
            #  If we're given a specific name, it must have that name
            if appname is not None and appnm != appname:
                continue
            #  We have to pay another stat() call to check if it's active.
            if is_version_dir(pathjoin(appdir,nm)):
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
        (_,ver,platform) = split_app_version(nm)
        if ver and platform:
            if is_version_dir(pathjoin(appdir,nm)):
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


def is_uninstalled_version_dir(vdir):
    """Check whether the given version directory is partially uninstalled.

    A partially-uninstalled version dir has had its "esky-bootstrap.txt"
    file renamed to "esky-bootstrap-old.txt".
    """
    return exists(pathjoin(vdir,"esky-bootstrap-old.txt"))


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


def get_original_filename(backname):
    """Given a backup filename, get the original name to which it refers.

    This is only really possible if the original file actually exists and
    is not guaranteed to be correct in all cases; but unless you do something
    silly it should work out OK.

    If no matching original file is found, None is returned.
    """
    filtered = ".".join(filter(lambda n: n != "old",backname.split(".")))
    for nm in listdir(dirname(backname)):
        if nm == backname:
            continue
        if filtered == ".".join(filter(lambda n: n != "old",nm.split("."))):
            return pathjoin(dirname(backname),nm)
    return None


_locked_version_dirs = {}

def lock_version_dir(vdir):
    """Lock the given version dir so it cannot be uninstalled."""
    if sys.platform == "win32":
        #  On win32, we just hold bootstrap file open for reading.
        #  This will prevent it from being renamed during uninstall.
        lockfile = pathjoin(vdir,"esky-bootstrap.txt")
        _locked_version_dirs.setdefault(vdir,[]).append(open(lockfile,"rt"))
    else:
        #  On posix platforms we take a shared flock on esky-lockfile.txt.
        #  While fcntl.fcntl locks are apparently the new hotness, they have
        #  unfortunate semantics that we don't want for this application:
        #      * not inherited across fork()
        #      * released when closing *any* fd associated with that file
        #  fcntl.flock doesn't have these problems, but may fail on NFS.
        #  To complicate matters, python sometimes emulated flock with fcntl!
        #  We therefore use a separate lock file to avoid unpleasantness.
        lockfile = pathjoin(vdir,"esky-lockfile.txt")
        f = open(lockfile,"r")
        _locked_version_dirs.setdefault(vdir,[]).append(f)
        fcntl.flock(f,fcntl.LOCK_SH)

def unlock_version_dir(vdir):
    """Unlock the given version dir, allowing it to be uninstalled."""
    _locked_version_dirs[vdir].pop().close()


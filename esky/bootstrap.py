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

If you want to compile your bootstrapping exes into standalone executables,
this module must also be written in the "RPython" dialect used by the PyPy
translation toolchain.

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

try:
    ESKY_CONTROL_DIR
except NameError:
    ESKY_CONTROL_DIR = "esky-files"

try:
    ESKY_APPDATA_DIR
except NameError:
    ESKY_APPDATA_DIR = "appdata"

try:
    __esky_name__
except NameError:
    __esky_name__ = ""

try:
    __rpython__
except NameError:
    __rpython__ = False

#  RPython doesn't handle SystemExit automatically, so we put the exit code
#  in this global var and catch SystemExit ourselves at the outmost scope.
_exit_code = [0]

#  The os module is not builtin, so we grab what we can from the
#  platform-specific modules and fudge the rest.
if "posix" in sys.builtin_module_names:
    import fcntl
    from posix import listdir, stat, unlink, rename, execv, getcwd, environ
    from posix import open as os_open
    from posix import read as os_read
    from posix import close as os_close
    SEP = "/"
    def isabs(path):
        return (path.startswith(SEP))
    def abspath(path):
        path = pathjoin(getcwd(),path)
        components_in = path.split(SEP)
        components = [components_in[0]]
        for comp in components_in[1:]:
            if not comp or comp == ".":
                pass
            elif comp == "..":
                components.pop()
            else:
                components.append(comp)
        return SEP.join(components)
elif "nt" in sys.builtin_module_names:
    fcntl = None
    import nt
    from nt import listdir, stat, unlink, rename, spawnv
    from nt import getcwd, P_WAIT, environ
    from nt import open as os_open
    from nt import read as os_read
    from nt import close as os_close
    SEP = "\\"
    def isabs(path):
        if path.startswith(SEP):
            return True
        if len(path) >= 2:
            if path[0].isalpha() and path[1] == ":":
                return True
        return False
    def abspath(path):
        path = pathjoin(getcwd(),path)
        components_in = path.split(SEP)
        components = [components_in[0]]
        for comp in components_in[1:]:
            if not comp or comp == ".":
                pass
            elif comp == "..":
                components.pop()
            else:
                components.append(comp)
        if path.startswith(SEP + SEP):
            components.insert(0, "")
        return SEP.join(components)
    #  The standard execv terminates the spawning process, which makes
    #  it impossible to wait for it.  This alternative is waitable, and
    #  uses the esky.slaveproc machinery to avoid leaving zombie children.
    def execv(filename,args):
        #  Create an O_TEMPORARY file and pass its name to the slave process.
        #  When this master process dies, the file will be deleted and the
        #  slave process will know to terminate.
        try:
            tdir = environ["TEMP"]
        except:
            tdir = None
        if tdir:
            try:
                nt.mkdir(pathjoin(tdir,"esky-slave-procs"),0600)
            except EnvironmentError:
                pass
            if exists(pathjoin(tdir,"esky-slave-procs")):
                flags = nt.O_CREAT|nt.O_EXCL|nt.O_TEMPORARY|nt.O_NOINHERIT
                for i in xrange(10):
                    tfilenm = "slave-%d.%d.txt" % (nt.getpid(),i,)
                    tfilenm = pathjoin(tdir,"esky-slave-procs",tfilenm)
                    try:
                        os_open(tfilenm,flags,0600)
                        args.insert(1,tfilenm)
                        args.insert(1,"--esky-slave-proc")
                        break
                    except EnvironmentError:
                        pass
        res = spawnv(P_WAIT,filename,args)
        _exit_code[0] = res
        raise SystemExit(res)
    #  A fake fcntl module which is false, but can fake out RPython
    class fcntl:
        LOCK_SH = 0
        def flock(self,fd,mode):
            pass
        def __nonzero__(self):
            return False
    fcntl = fcntl()
else:
    raise RuntimeError("unsupported platform: " + sys.platform)


if __rpython__:
    # RPython provides ll hooks for the actual os.environ object, not the
    # one we pulled out of "nt" or "posix".
    from os import environ

    # RPython doesn't have access to the "sys" module, so we fake it out.
    # The entry_point function will set these value appropriately.
    _sys = sys
    class sys:
        platform = _sys.platform
        executable = _sys.executable
        argv = _sys.argv
        version_info = _sys.version_info
        modules = {}
        builtin_module_names = _sys.builtin_module_names
        def exit(self,code):
            _exit_code[0] = code
            raise SystemExit(code)
        def exc_info(self):
            return None,None,None
    sys = sys()
    sys.modules["sys"] = sys

    #  RPython doesn't provide the sorted() builtin, and actually makes sorting
    #  quite complicated in general.  I can't convince the type annotator to be
    #  happy about using their "listsort" module, so I'm doing my own using a
    #  simple insertion sort.  We're only sorting short lists and they always
    #  contain (list(str),str), so this should do for now.
    def _list_gt(l1,l2):
        i = 0
        while i < len(l1) and i < len(l2):
            if l1[i] > l2[i]:
               return True
            if l1[i] < l2[i]:
               return False
            i += 1
        if len(l1) > len(l2):
            return True
        return False
    def sorted(lst,reverse=False):
        slst = []
        if reverse:
            for item in lst:
                for j in xrange(len(slst)):
                    if not _list_gt(slst[j][0],item[0]):
                        slst.insert(j,item)
                        break 
                else:
                    slst.append(item)
        else:
            for item in lst:
                for j in xrange(len(slst)):
                    if _list_gt(slst[j][0],item[0]):
                        slst.insert(j,item)
                        break 
                else:
                    slst.append(item)
        return slst
    # RPython doesn't provide the "zfill" or "isalnum" methods on strings.
    def zfill(str,n):
        while len(str) < n:
            str = "0" + str
        return str
    def isalnum(str):
        for c in str:
            if not c.isalnum():
                return False
        return True
    # RPython doesn't provide the "fcntl" module.  Fake it.
    # TODO: implement it using externals
    if fcntl:
        class fcntl:
            LOCK_SH = fcntl.LOCK_SH
            def flock(self,fd,mode):
                pass
        fcntl = fcntl()
else:
    #  We need to use a compatability wrapper for some string methods missing
    #  in RPython, since we can't just add them as methods on the str type.
    def zfill(str,n):
        return str.zfill(n)
    def isalnum(str):
        return str.isalnum()


def pathjoin(*args):
    """Local re-implementation of os.path.join."""
    path = args[0]
    for arg in list(args[1:]):
        if isabs(arg):
            path = arg
        else:
            while path.endswith(SEP):
                path = path[:-1]
            path = path + SEP + arg
    return path

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
        # TODO: how to get the errno under RPython?
        if not __rpython__:
            if e.errno not in (errno.ENOENT,errno.ENOTDIR,errno.ESRCH,):
                raise
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
    chainloads that version of the application.
    """
    sys.executable = abspath(sys.executable)
    appdir = appdir_from_executable(sys.executable)
    vsdir = pathjoin(appdir,ESKY_APPDATA_DIR)
    # TODO: remove compatability hook for ESKY_APPDATA_DIR="".
    best_version = None
    try:
        if __esky_name__:
            best_version = get_best_version(vsdir,appname=__esky_name__)
        if best_version is None:
            best_version = get_best_version(vsdir)
        if best_version is None:
            if exists(vsdir):
                raise RuntimeError("no usable frozen versions were found")
            else:
                raise EnvironmentError
    except EnvironmentError:
        if exists(vsdir):
            raise
        vsdir = appdir
        if __esky_name__:
            best_version = get_best_version(vsdir,appname=__esky_name__)
        if best_version is None:
            best_version = get_best_version(vsdir)
        if best_version is None:
            raise RuntimeError("no usable frozen versions were found")
    return chainload(pathjoin(vsdir,best_version))


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
        if exists(dirname(target_dir)):
            bsfile = pathjoin(target_dir,ESKY_CONTROL_DIR)
            bsfile = pathjoin(bsfile,"bootstrap-manifest.txt")
            if not exists(bsfile):
                execv(sys.executable,list(sys.argv))
                return
        raise
    else:
        #  If all goes well, we can actually launch the target version.
        _chainload(target_dir)


def get_exe_locations(target_dir):
    """Generate possible locations from which to chainload in the target dir."""
    # TODO: let this be a generator when not compiling with PyPy, so we can
    # avoid a few stat() calls in the common case.
    locs = []
    appdir = appdir_from_executable(sys.executable)
    #  If we're in an appdir, first try to launch from within "<appname>.app"
    #  directory.  We must also try the default scheme for backwards compat.
    if sys.platform == "darwin":
        if basename(dirname(sys.executable)) == "MacOS":
            if __esky_name__:
                locs.append(pathjoin(target_dir,
                                     __esky_name__+".app",
                                     sys.executable[len(appdir)+1:]))
            else:
                for nm in listdir(target_dir):
                    if nm.endswith(".app"):
                        locs.append(pathjoin(target_dir,
                                             nm,
                                             sys.executable[len(appdir)+1:]))
    #  This is the default scheme: the same path as the exe in the appdir.
    locs.append(target_dir + sys.executable[len(appdir):])
    #  If sys.executable was a backup file, try using original filename.
    orig_exe = get_original_filename(sys.executable)
    if orig_exe is not None:
        locs.append(target_dir + orig_exe[len(appdir):])
    return locs


def verify(target_file):
    """Verify the integrity of the given target file.

    By default this is a no-op; override it to provide e.g. signature checks.
    """
    pass


def _chainload(target_dir):
    """Default implementation of the chainload() function.

    Specific freezer modules may provide a more efficient, reliable or
    otherwise better version of this function.
    """
    exc_type,exc_value,traceback = None,None,None
    for target_exe in get_exe_locations(target_dir):
        verify(target_exe)
        try:
            execv(target_exe,[target_exe] + sys.argv[1:])
            return
        except EnvironmentError, exc_value:
            #  Careful, RPython lacks a usable exc_info() function.
            exc_type,_,traceback = sys.exc_info()
            if not __rpython__:
                if exc_value.errno != errno.ENOENT:
                    raise
            else:
                if exists(target_exe):
                    raise
    else:
        if exc_value is not None:
            if exc_type is not None:
                raise exc_type,exc_value,traceback
            else:
                raise exc_value
        raise RuntimeError("couldn't chainload any executables")


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

    Currently it only need contain the "esky-files/bootstrap-mainfest.txt" file.
    """
    if exists(pathjoin(vdir,ESKY_CONTROL_DIR,"bootstrap-manifest.txt")):
        return True
    return False


def is_installed_version_dir(vdir):
    """Check whether the given version directory is fully installed.

    Currently, a completed installation is indicated by the lack of an
    "esky-files/bootstrap" directory.
    """
    if not exists(pathjoin(vdir,ESKY_CONTROL_DIR,"bootstrap")):
        return True
    return False


def is_uninstalled_version_dir(vdir):
    """Check whether the given version directory is partially uninstalled.

    A partially-uninstalled version dir has had the "bootstrap-manifest.txt"
    renamed to "bootstrap-manifest-old.txt".
    """
    if exists(pathjoin(vdir,ESKY_CONTROL_DIR,"bootstrap-manifest-old.txt")):
        return True
    return False
    


def split_app_version(s):
    """Split an app version string to name, version and platform components.

    For example, app-name-0.1.2.win32 => ("app-name","0.1.2","win32")
    """
    bits = s.split("-")
    idx = 1
    while idx < len(bits):
        if bits[idx]:
            if not bits[idx][0].isalpha() or not isalnum(bits[idx]):
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

    This function returns a sequence of strings that compares with the results
    for other versions in a chronologically sensible way.  You'd use it to
    compare two version strings like so:

        if parse_version("1.9.2") > parse_version("1.10.0"):
            raise RuntimeError("what rubbish, that's an older version!")

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
    return parts


_replace_p = {'pre':'c', 'preview':'c','-':'final-','rc':'c','dev':'@'}.get
def _parse_version_parts(s):
    parts = []
    for part in _split_version_components(s):
        part = _replace_p(part,part)
        if not part or part=='.':
            continue
        if part[:1] in '0123456789':
            parts.append(zfill(part,8))    # pad for numeric comparison
        else:
            parts.append('*'+part)
    parts.append('*final')  # ensure that alpha/beta/candidate are before final
    return parts


def _split_version_components(s):
    """Split version string into individual tokens.

    pkg_resources does this using a regexp: (\d+ | [a-z]+ | \.| -)
    Unfortunately the 're' module isn't in the bootstrap, so we have to do
    an equivalent parse by hand.  Forunately, that's pretty easy.
    """
    comps = []
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
        comps.append(s[start:end])
        start = end
    return comps


def get_original_filename(backname):
    """Given a backup filename, get the original name to which it refers.

    This is only really possible if the original file actually exists and
    is not guaranteed to be correct in all cases; but unless you do something
    silly it should work out OK.

    If no matching original file is found, None is returned.
    """
    filtered = ".".join([n for n in backname.split(".") if n != "old"])
    for nm in listdir(dirname(backname)):
        if nm == backname:
            continue
        if filtered == ".".join([n for n in nm.split(".") if n != "old"]):
            return pathjoin(dirname(backname),nm)
    return None


_locked_version_dirs = {}

def lock_version_dir(vdir):
    """Lock the given version dir so it cannot be uninstalled."""
    if sys.platform == "win32":
        #  On win32, we just hold bootstrap file open for reading.
        #  This will prevent it from being renamed during uninstall.
        lockfile = pathjoin(vdir,ESKY_CONTROL_DIR,"bootstrap-manifest.txt")
        _locked_version_dirs.setdefault(vdir,[]).append(os_open(lockfile,0,0))
    else:
        #  On posix platforms we take a shared flock on esky-files/lockfile.txt.
        #  While fcntl.fcntl locks are apparently the new hotness, they have
        #  unfortunate semantics that we don't want for this application:
        #      * not inherited across fork()
        #      * released when closing *any* fd associated with that file
        #  fcntl.flock doesn't have these problems, but may fail on NFS.
        #  To complicate matters, python sometimes emulates flock with fcntl!
        #  We therefore use a separate lock file to avoid unpleasantness.
        lockfile = pathjoin(vdir,ESKY_CONTROL_DIR,"lockfile.txt")
        f = os_open(lockfile,0,0)
        _locked_version_dirs.setdefault(vdir,[]).append(f)
        fcntl.flock(f,fcntl.LOCK_SH)

def unlock_version_dir(vdir):
    """Unlock the given version dir, allowing it to be uninstalled."""
    os_close(_locked_version_dirs[vdir].pop())

if __rpython__:
    def main():
        bootstrap()
    def target(driver,args):
        """Target function for compiling a standalone bootstraper with PyPy."""
        def entry_point(argv):
             exit_code = 0
             #  TODO: resolve symlinks etc
             sys.executable = abspath(pathjoin(getcwd(),argv[0]))
             sys.argv = argv
             try:
                 main()
             except SystemExit, e:
                 exit_code = _exit_code[0]
             return exit_code
        return entry_point, None


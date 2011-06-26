#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.util:  misc utility functions for esky

"""

from __future__ import with_statement
from __future__ import absolute_import

import sys
import errno

#  Since esky apps are required to call the esky.run_startup_hooks() method on
#  every invocation, we want as little overhead as possible when importing
#  the main module.  We therefore use a simple lazy-loading scheme for many
#  of our imports, built from the functions below.

def lazy_import(func):
    """Decorator for declaring a lazy import.

    This decorator turns a function into an object that will act as a lazy
    importer.  Whenever the object's attributes are accessed, the function
    is called and its return value used in place of the object.  So you
    can declare lazy imports like this:

        @lazy_import
        def socket():
            import socket
            return socket

    The name "socket" will then be bound to a transparent object proxy which
    will import the socket module upon first use.
 
    The syntax here is slightly more verbose than other lazy import recipes,
    but it's designed not to hide the actual "import" statements from tools
    like py2exe or grep.
    """
    try:
        f = sys._getframe(1)
    except Exception:
        namespace = None
    else:
        namespace = f.f_locals
    return _LazyImport(func.func_name,func,namespace)


class _LazyImport(object):
    """Class representing a lazy import."""

    def __init__(self,name,loader,namespace=None):
        self._esky_lazy_target = _LazyImport
        self._esky_lazy_name = name
        self._esky_lazy_loader = loader
        self._esky_lazy_namespace = namespace

    def _esky_lazy_load(self):
        if self._esky_lazy_target is _LazyImport:
            self._esky_lazy_target = self._esky_lazy_loader()
            ns = self._esky_lazy_namespace
            if ns is not None:
                try: 
                    if ns[self._esky_lazy_name] is self:
                        ns[self._esky_lazy_name] = self._esky_lazy_target
                except KeyError:
                    pass

    def __getattribute__(self,attr):
        try:
            return object.__getattribute__(self,attr)
        except AttributeError:
            if self._esky_lazy_target is _LazyImport:
                self._esky_lazy_load()
            return getattr(self._esky_lazy_target,attr)

    def __nonzero__(self):
        if self._esky_lazy_target is _LazyImport:
            self._esky_lazy_load()
        return bool(self._esky_lazy_target)


@lazy_import
def os():
    import os
    return os

@lazy_import
def shutil():
    import shutil
    return shutil

@lazy_import
def time():
    import time
    return time

@lazy_import
def re():
    import re
    return re

@lazy_import
def zipfile():
    import zipfile
    return zipfile

@lazy_import
def itertools():
    import itertools
    return itertools

@lazy_import
def StringIO():
    try:
        import cStringIO as StringIO
    except ImportError:
        import StringIO
    return StringIO

@lazy_import
def distutils():
    import distutils
    import distutils.log   # need to prompt cxfreeze about this dep
    import distutils.util
    return distutils


from esky.bootstrap import appdir_from_executable as _bs_appdir_from_executable
from esky.bootstrap import get_best_version, get_all_versions,\
                           is_version_dir, is_installed_version_dir,\
                           is_uninstalled_version_dir,\
                           split_app_version, join_app_version, parse_version,\
                           get_original_filename, lock_version_dir,\
                           unlock_version_dir, fcntl, ESKY_CONTROL_DIR,\
                           ESKY_APPDATA_DIR


def files_differ(file1,file2,start=0,stop=None):
    """Check whether two files are actually different."""
    try:
        stat1 = os.stat(file1)
        stat2 = os.stat(file2)
    except EnvironmentError:
         return True
    if stop is None and stat1.st_size != stat2.st_size:
        return True
    f1 = open(file1,"rb")
    try:
        f2 = open(file2,"rb")
        if start >= stat1.st_size:
            return False
        elif start < 0:
            start = stat1.st_size + start
        if stop is None or stop > stat1.st_size:
            stop = stat1.st_size
        elif stop < 0:
            stop = stat1.st_size + stop
        if stop <= start:
            return False
        toread = stop - start
        f1.seek(start)
        f2.seek(start)
        try:
            sz = min(1024*256,toread)
            data1 = f1.read(sz)
            data2 = f2.read(sz)
            while sz > 0 and data1 and data2:
                if data1 != data2:
                    return True
                toread -= sz
                sz = min(1024*256,toread)
                data1 = f1.read(sz)
                data2 = f2.read(sz)
            return (data1 != data2)
        finally:
            f2.close()
    finally:
        f1.close()


def pairwise(iterable):
    """Iterator over pairs of elements from the given iterable."""
    a,b = itertools.tee(iterable)
    try:
        b.next()
    except StopIteration:
        pass
    return itertools.izip(a,b)


def common_prefix(iterables):
    """Find the longest common prefix of a series of iterables."""
    iterables = iter(iterables)
    try:
        prefix = iterables.next()
    except StopIteration:
        raise ValueError("at least one iterable is required")
    for item in iterables:
        count = 0
        for (c1,c2) in itertools.izip(prefix,item):
            if c1 != c2:
                break
            count += 1
        prefix = prefix[:count]
    return prefix


def appdir_from_executable(exepath):
    """Find the top-level application directory, given sys.executable."""
    #  The standard layout is <appdir>/ESKY_APPDATA_DIR/<vdir>/<exepath>.
    #  Stripping of <exepath> is done by _bs_appdir_from_executable.
    vdir = _bs_appdir_from_executable(exepath)
    appdir = os.path.dirname(vdir)
    #  On OSX we sometimes need to strip an additional directory since the
    #  app can be contained in an <appname>.app directory.
    if sys.platform == "darwin" and is_version_dir(appdir):
        appdir = os.path.dirname(appdir)
    # TODO: remove compatability hook for ESKY_APPDATA_DIR=""
    if ESKY_APPDATA_DIR and os.path.basename(appdir) == ESKY_APPDATA_DIR:
        appdir = os.path.dirname(appdir)
    return appdir


def appexe_from_executable(exepath):
    """Find the top-level application executable, given sys.executable."""
    appdir = appdir_from_executable(exepath)
    exename = os.path.basename(exepath)
    #  On OSX we might be in a bundle, run from Contents/MacOS/<exename>
    if sys.platform == "darwin":
        if os.path.isdir(os.path.join(appdir,"Contents","MacOS")):
            return os.path.join(appdir,"Contents","MacOS",exename)
    return os.path.join(appdir,exename)


def extract_zipfile(source,target,name_filter=None):
    """Extract the contents of a zipfile into a target directory.

    The argument 'source' names the zipfile to read, while 'target' names
    the directory into which to extract.  If given, the optional argument
    'name_filter' must be a function mapping names from the zipfile to names
    in the target directory.
    """
    zf = zipfile.ZipFile(source,"r")
    try:
        if hasattr(zf,"open"):
            zf_open = zf.open
        else:
            def zf_open(nm,mode):
                return StringIO.StringIO(zf.read(nm))
        for nm in zf.namelist():
            if nm.endswith("/"):
                continue
            if name_filter:
                outfilenm = name_filter(nm)
                if outfilenm is None:
                    continue
                outfilenm = os.path.join(target,outfilenm)
            else:
                outfilenm = os.path.join(target,nm)
            if not os.path.isdir(os.path.dirname(outfilenm)):
                os.makedirs(os.path.dirname(outfilenm))
            infile = zf_open(nm,"r")
            try:
                outfile = open(outfilenm,"wb")
                try:
                    shutil.copyfileobj(infile,outfile)
                finally:
                    outfile.close()
            finally:
                infile.close()
            mode = zf.getinfo(nm).external_attr >> 16L
            if mode:
                os.chmod(outfilenm,mode)
    finally:
        zf.close()


def zipfile_common_prefix_dir(source):
    """Find the common prefix directory of all files in a zipfile."""
    zf = zipfile.ZipFile(source)
    prefix = common_prefix(zf.namelist())
    if "/" in prefix:
        return prefix.rsplit("/",1)[0] + "/"
    else:
        return ""


def deep_extract_zipfile(source,target,name_filter=None):
    """Extract the deep contents of a zipfile into a target directory.

    This is just like extract_zipfile() except that any common prefix dirs
    are removed.  For example, if everything in the zipfile is under the
    directory "example.app" then that prefix will be removed during unzipping.

    This is useful to allow distribution of "friendly" zipfiles that don't
    overwrite files in the current directory when extracted by hand.
    """
    prefix = zipfile_common_prefix_dir(source)
    if prefix:
        def new_name_filter(nm):
            if not nm.startswith(prefix):
                return None
            if name_filter is not None:
                return name_filter(nm[len(prefix):])
            return nm[len(prefix):]
    else:
         new_name_filter = name_filter
    return extract_zipfile(source,target,new_name_filter)



def create_zipfile(source,target,get_zipinfo=None,members=None,compress=None):
    """Bundle the contents of a given directory into a zipfile.

    The argument 'source' names the directory to read, while 'target' names
    the zipfile to be written.

    If given, the optional argument 'get_zipinfo' must be a function mapping
    filenames to ZipInfo objects.  It may also return None to indicate that
    defaults should be used, or a string to indicate that defaults should be
    used with a new archive name.

    If given, the optional argument 'members' must be an iterable yielding
    names or ZipInfo objects.  Files will be added to the archive in the
    order specified by this function.

    If the optional argument 'compress' is given, it must be a bool indicating
    whether to compress the files by default.  The default is no compression.
    """
    if not compress:
        compress_type = zipfile.ZIP_STORED
    else:
        compress_type = zipfile.ZIP_DEFLATED
    zf = zipfile.ZipFile(target,"w",compression=compress_type)
    if members is None:
        def gen_members():
            for (dirpath,dirnames,filenames) in os.walk(source):
                for fn in filenames:
                    yield os.path.join(dirpath,fn)[len(source)+1:]
        members = gen_members()
    for fpath in members:
        if isinstance(fpath,zipfile.ZipInfo):
            zinfo = fpath
            fpath = os.path.join(source,zinfo.filename)
        else:
            if get_zipinfo:
                zinfo = get_zipinfo(fpath)
            else:
                zinfo = None
            fpath = os.path.join(source,fpath)
        if zinfo is None:
            zf.write(fpath,fpath[len(source)+1:])
        elif isinstance(zinfo,basestring):
            zf.write(fpath,zinfo)
        else:
            with open(fpath,"rb") as f:
                zf.writestr(zinfo,f.read())
    zf.close()


_CACHED_PLATFORM = None
def get_platform():
    """Get the platform identifier for the current platform.

    This is similar to the function distutils.util.get_platform(); it returns
    a string identifying the types of platform on which binaries built on this
    machine can reasonably be expected to run.

    Unlike distutils.util.get_platform(), the value returned by this function
    is guaranteed not to contain any periods. This makes it much easier to
    parse out of filenames.
    """
    global _CACHED_PLATFORM
    if _CACHED_PLATFORM is None:
        _CACHED_PLATFORM = distutils.util.get_platform().replace(".","_")
    return _CACHED_PLATFORM
 

def is_core_dependency(filenm):
    """Check whether than named file is a core python dependency.

    If it is, then it's required for any frozen program to run (even the 
    bootstrapper).  Currently this includes only the python DLL and the
    MSVCRT private assembly.
    """
    if re.match("^(lib)?python\\d[\\d\\.]*\\.[a-z\d\\.]*$",filenm):
        return True
    if filenm.startswith("Microsoft.") and filenm.endswith(".CRT"):
        return True
    return False


def copy_ownership_info(src,dst,cur="",default=None):
    """Copy file ownership from src onto dst, as much as possible."""
    # TODO: how on win32?
    source = os.path.join(src,cur)
    target = os.path.join(dst,cur)
    if default is None:
        default = os.stat(src)
    if os.path.exists(source):
        info = os.stat(source)
    else:
        info = default
    if sys.platform != "win32":
        os.chown(target,info.st_uid,info.st_gid)
    if os.path.isdir(target):
        for nm in os.listdir(target):
            copy_ownership_info(src,dst,os.path.join(cur,nm),default)



def get_backup_filename(filename):
    """Get the name to which a backup of the given file can be written.

    This will typically the filename with ".old" inserted at an appropriate
    location.  We try to preserve the file extension where possible.
    """
    parent = os.path.dirname(filename)
    parts = os.path.basename(filename).split(".")
    parts.insert(-1,"old")
    backname = os.path.join(parent,".".join(parts))
    while os.path.exists(backname):
        parts.insert(-1,"old")
        backname = os.path.join(parent,".".join(parts))
    return backname


def is_locked_version_dir(vdir):
    """Check whether the given version dir is locked."""
    if sys.platform == "win32":
        lockfile = os.path.join(vdir,ESKY_CONTROL_DIR,"bootstrap-manifest.txt")
        try:
            os.rename(lockfile,lockfile)
        except EnvironmentError:
            return True
        else:
            return False
    else:
        lockfile = os.path.join(vdir,ESKY_CONTROL_DIR,"lockfile.txt")
        f = open(lockfile,"r")
        try:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except EnvironmentError, e:
            if e.errno not in (errno.EACCES,errno.EAGAIN,):
                raise
            return True
        else:
            return False
        finally:
            f.close()


def really_rename(source,target):
    """Like os.rename, but try to work around some win32 wierdness.

    Every so often windows likes to throw a spurious error about not being
    able to rename something; if we sleep for a brief period and try
    again it seems to get over it.
    """
    if sys.platform != "win32":
        os.rename(source,target)
    else:
        for _ in xrange(10):
            try:
                os.rename(source,target)
            except WindowsError, e:
                if e.errno not in (errno.EACCES,):
                    raise
                time.sleep(0.01)
            else:
                break
        else:
            os.rename(source,target)


def really_rmtree(path):
    """Like shutil.rmtree, but try to work around some win32 wierdness.

    Every so often windows likes to throw a spurious error about not being
    able to remove a directory - like claiming it still contains files after
    we just deleted all the files in the directory.  If we sleep for a brief
    period and try again it seems to get over it.
    """
    if sys.platform != "win32":
        shutil.rmtree(path)
    else:
        #  If it's going to error out legitimately, let it do so.
        if not os.path.exists(path):
            shutil.rmtree(path)
        #  This is a little retry loop that catches troublesome errors.
        for _ in xrange(10):
            try:
                shutil.rmtree(path)
            except WindowsError, e:
                if e.errno in (errno.ENOTEMPTY,errno.EACCES,):
                    time.sleep(0.01)
                elif e.errno == errno.ENOENT:
                    if not os.path.exists(path):
                        return
                    time.sleep(0.01)
                else:
                    raise
            else:
                break
        else:
            shutil.rmtree(path)



#  Copyright (c) 2009, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.util:  misc utility functions for esky

"""

import os
import re
import shutil
import zipfile
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from distutils.util import get_platform as _distutils_get_platform

from esky.bootstrap import get_best_version, get_all_versions, \
                           is_version_dir, is_installed_version_dir, \
                           is_uninstalled_version_dir, \
                           split_app_version, join_app_version, parse_version
from esky.bootstrap import appdir_from_executable as _bs_appdir_from_executable


def appdir_from_executable(exepath):
    """Find the top-level application directory, given sys.executable."""
    vdir = _bs_appdir_from_executable(exepath)
    return os.path.dirname(vdir)


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
                return StringIO(zf.read(nm))
        for nm in zf.namelist():
            if nm.endswith("/"):
                continue
            if name_filter:
                outfilenm = os.path.join(target,name_filter(nm))
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


def create_zipfile(source,target,get_zipinfo=None,members=None,compress=None):
    """Bundle the contents of a given directory into a zipfile.

    The argument 'source' names the directory to read, while 'target' names
    the zipfile to be written.

    If given, the optional argument 'get_zipinfo' must be a function mapping
    filenames to ZipInfo objects.  It may also return None to indicate that
    defaults should be used.

    If given, the optional argument 'members' must be an iterable yeilding
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
        else:
            with open(fpath,"rb") as f:
                zf.writestr(zinfo,f.read())
    zf.close()


def get_platform():
    """Get the platform identifier for the current platform.

    This is similar to the function distutils.util.get_platform() - it returns
    a string identifying the types of platform on which binaries built on this
    machine can reasonably be expected to run.

    Unlike distutils.util.get_platform(), the value returned by this function
    is guaranteed not to contain any periods; this makes it much easier to
    parse out of filenames.
    """
    return _distutils_get_platform().replace(".","_")
 

def is_core_dependency(filenm):
    """Check whether than named file is a core python dependency.

    If it is, then it's required for any frozen program to run (even the 
    bootstrapper).  Currently this includes only the python DLL and the
    MSVCRT private assembly.
    """
    if re.match("^(lib)?python\\d[\\d\\.]*\\.[a-z\\.]*$",filenm):
        return True
    if filenm.startswith("Microsoft.") and filenm.endswith(".CRT"):
        return True
    return False



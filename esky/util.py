#  Copyright (c) 2009, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.util:  misc utility functions for esky

"""

import os
import re
import shutil
import zipfile

from distutils.util import get_platform as _distutils_get_platform


def extract_zipfile(source,target,name_filter=None):
    """Extract the contents of a zipfile into a target directory.

    The argument 'source' names the zipfile to read, while 'target' names
    the directory into which to extract.  If given, the optional argument
    'name_filter' must be a function mapping names from the zipfile to names
    in the target directory.
    """
    zf = zipfile.ZipFile(source,"r")
    for nm in zf.namelist():
        if name_filter:
            outfilenm = os.path.join(target,name_filter(nm))
        else:
            outfilenm = os.path.join(target,nm)
        if not os.path.isdir(os.path.dirname(outfilenm)):
            os.makedirs(os.path.dirname(outfilenm))
        infile = zf.open(nm,"r")
        try:
            outfile = open(outfilenm,"wb")
            try:
                shutil.copyfileobj(infile,outfile)
            finally:
                outfile.close()
        finally:
            infile.close()
        mode = zf.getinfo(nm).external_attr >> 16L
        os.chmod(outfilenm,mode)


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
    bootstrapper).  Currently this includes only the python DLL.
    """
    return re.match("^(lib)?python\\d[\\d\\.]*\\.[a-z\\.]*$",filenm)



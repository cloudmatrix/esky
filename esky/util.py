#  Copyright (c) 2009, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.util:  misc utilities for esky

"""

import os
import shutil
import zipfile


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
 

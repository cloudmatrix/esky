
import os
import imp
import time
import zipfile
import marshal
import struct
import shutil
import inspect

import bbfreeze
from bbfreeze.freezer import replace_paths_in_code

import esky.bootstrap

# Things to do:
#
#   * bundle package_data into the library.zip
#   * copy data_files into the distribution directory
#


def freeze_esky(e):
    fdir = os.path.join(e.distdir,"%s-%s"%(e.name,e.version,))
    f = bbfreeze.Freezer(fdir,e.includes,e.excludes)
    f.linkmethod = "loader"
    f.addModule("esky")
    for s in e.scripts:
        f.addScript(s,gui_only=s.endswith(".pyw"))
    f()
    bscode_source = inspect.getsource(esky.bootstrap)
    bscode = imp.get_magic() + struct.pack("<i",time.time())
    bscode += marshal.dumps(compile(bscode_source,"__main__.py","exec"))
    bslib_path = os.path.join(fdir,"bootstrap-library.zip")
    bslib = zipfile.PyZipFile(bslib_path,"w",zipfile.ZIP_STORED)
    bslib.writestr("__main__.pyc",bscode)
    bslib.close()
    shutil.copy(bslib_path,os.path.join(e.distdir,"library.zip"))
    for s in e.scripts:
        nm = os.path.basename(s)
        if nm.endswith(".py"):
            nm = nm[:-3]
        # TODO: add .exe on windows
        shutil.copy(os.path.join(fdir,nm),os.path.join(e.distdir,nm))


#  Copyright (c) 2009, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.bdist_esky.f_py2exe:  bdist_esky support for py2exe

"""


import os
import re
import sys
import imp
import time
import zipfile
import marshal
import struct
import shutil
import inspect
import zipfile
from glob import glob


from py2exe.build_exe import py2exe

import esky
from esky.util import is_core_dependency
from esky import winres


def freeze(dist):
    """Freeze the given distribution data using bbfreeze."""
    includes = dist.includes
    excludes = dist.excludes
    options = dist.freezer_options
    #  Merge in any encludes/excludes given in freezer_options
    includes.append("esky")
    for inc in options.pop("includes",()):
        includes.append(inc)
    for exc in options.pop("excludes",()):
        excludes.append(exc)
    #  py2exe expects some arguments on the main distribution object
    dist.distribution.console = []
    dist.distribution.windows = []
    my_data_files = dist.distribution.data_files
    dist.distribution.data_files = []
    for script in dist.get_scripts():
        if script.endswith(".pyw"):
            dist.distribution.windows.append(script)
        else:
            dist.distribution.console.append(script)
    if "zipfile" in options:
        dist.distribution.zipfile = options.pop("zipfile")
    #  Create the py2exe cmd and adjust its options
    cmd = py2exe(dist.distribution)
    cmd.includes = includes
    cmd.excludes = excludes
    for (nm,val) in options.iteritems():
        setattr(cmd,nm,val)
    cmd.finalize_options()
    cmd.dist_dir = dist.freeze_dir
    #  OK, actually run the freeze process
    cmd.run()
    #  Copy data files into the freeze dir
    dist.distribution.data_files = my_data_files
    for (src,dst) in dist.get_data_files():
        dst = os.path.join(dist.freeze_dir,dst)
        dstdir = os.path.dirname(dst)
        if not os.path.isdir(dstdir):
            dist.mkpath(dstdir)
        dist.copy_file(src,dst)
    #  Copy package data into the library.zip
    if dist.distribution.zipfile is not None:
        lib = zipfile.ZipFile(os.path.join(dist.freeze_dir,"library.zip"),"a")
        for (src,arcnm) in dist.get_package_data():
            lib.write(src,arcnm)
        lib.close()
    else:
        for (src,arcnm) in dist.get_package_data():
            err = "zipfile=None can't be used with package_data (yet...)"
            raise RuntimeError(err)
    #  There's no need to copy library.zip into the bootstrap env, as the
    #  chainloader will run before it tries to look for it.
    #  Create the bootstraping code, using custom code if specified.
    code_source = [inspect.getsource(esky.bootstrap)]
    code_source.append(_FAKE_ESKY_BOOTSTRAP_MODULE)
    if dist.bootstrap_module is None:
        code_source.append("bootstrap()")
    else:
        bsmodule = __import__(dist.bootstrap_module)
        for submod in dist.boostrap_module.split(".")[1:]:
            bsmodule = getattr(bsmodule,submod)
        code_source.append(inspect.getsource(bsmodule))
    code_source = "\n".join(code_source)
    code = marshal.dumps([compile(code_source,"__main__.py","exec")])
    #  This magic format is taken straight from the py2exe source code.
    coderes = struct.pack("iiii",
                     0x78563412, # a magic value used for integrity checking,
                     0, # no optimization
                     False,  # normal buffered output
                     len(code),
                     ) + "\000" + code + "\000"
    #  Copy the loader program for each script into the bootstrap env, and
    #  insert the bootstrap code into it as a resource.
    #  This appears to have the happy side-effect of stripping any extra
    #  data from the end of the exe, which is exactly what we want when
    #  bundling all the deps in an attached zipfile.
    for script in dist.get_scripts():
        nm = os.path.basename(script)
        if nm.endswith(".py") or nm.endswith(".pyw"):
            nm = ".".join(nm.split(".")[:-1]) + ".exe"
        exepath = dist.copy_to_bootstrap_env(nm)
        winres.add_resource(exepath,coderes,u"PYTHONSCRIPT",1,0)
    #  Copy any core dependencies into the bootstrap env
    for nm in os.listdir(dist.freeze_dir):
        if is_core_dependency(nm):
            dist.copy_to_bootstrap_env(nm)


#  Code to fake out any bootstrappers that try to import from esky.
_FAKE_ESKY_BOOTSTRAP_MODULE = """
class __fake:
  __all__ = ()
sys.modules["esky"] = __fake()
sys.modules["esky.bootstrap"] = __fake()
"""



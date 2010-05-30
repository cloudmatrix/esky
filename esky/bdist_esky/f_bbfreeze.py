#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.bdist_esky.f_bbfreeze:  bdist_esky support for bbfreeze

"""


import os
import re
import sys
import imp
import time
import zipfile
import tempfile
import marshal
import struct
import shutil
import inspect
import zipfile
from glob import glob


import bbfreeze

import esky
from esky.util import is_core_dependency


def freeze(dist):
    """Freeze the given distribution data using bbfreeze."""
    includes = dist.includes
    excludes = dist.excludes
    options = dist.freezer_options
    #  Merge in any encludes/excludes given in freezer_options
    for inc in options.pop("includes",()):
        includes.append(inc)
    for exc in options.pop("excludes",()):
        excludes.append(exc)
    #  Freeze up the given scripts
    f = bbfreeze.Freezer(dist.freeze_dir,includes=includes,excludes=excludes)
    for (nm,val) in options.iteritems():
        setattr(f,nm,val)
    f.addModule("esky")
    tdir = tempfile.mkdtemp()
    try:
        for exe in dist.get_executables():
            f.addScript(exe.script,gui_only=exe.gui_only)
        if "include_py" not in options:
            f.include_py = False
        if "linkmethod" not in options:
            #  Since we're going to zip it up, the benefits of hard-
            #  or sym-linking the loader exe will mostly be lost.
            f.linkmethod = "loader"
        f()
    finally:
        shutil.rmtree(tdir)
    #  Copy data files into the freeze dir
    for (src,dst) in dist.get_data_files():
        dst = os.path.join(dist.freeze_dir,dst)
        dstdir = os.path.dirname(dst)
        if not os.path.isdir(dstdir):
            dist.mkpath(dstdir)
        dist.copy_file(src,dst)
    #  Copy package data into the library.zip
    lib = zipfile.ZipFile(os.path.join(dist.freeze_dir,"library.zip"),"a")
    for (src,arcnm) in dist.get_package_data():
        lib.write(src,arcnm)
    lib.close()
    #  Create the bootstrap code, using custom code if specified.
    code_source = [inspect.getsource(esky.bootstrap)]
    if sys.platform == "win32":
        code_source.append(_CUSTOM_WIN32_CHAINLOADER)
    code_source.append("__esky_name__ = '%s'" % (dist.distribution.get_name(),))
    if dist.bootstrap_module is None:
        code_source.append("bootstrap()")
    else:
        code_source.append("__name__ = '__main__'")
        bsmodule = __import__(dist.bootstrap_module)
        for submod in dist.bootstrap_module.split(".")[1:]:
            bsmodule = getattr(bsmodule,submod)
        code_source.append(inspect.getsource(bsmodule))
        code_source.append("raise RuntimeError('didnt chainload')")
    code_source = "\n".join(code_source)
    maincode = imp.get_magic() + struct.pack("<i",0)
    maincode += marshal.dumps(compile(code_source,"__main__.py","exec"))
    #  Create code for a fake esky.bootstrap module
    eskycode = imp.get_magic() + struct.pack("<i",0)
    eskycode += marshal.dumps(compile("","esky/__init__.py","exec"))
    eskybscode = imp.get_magic() + struct.pack("<i",0)
    eskybscode += marshal.dumps(compile("","esky/bootstrap.py","exec"))
    #  Store bootstrap code as __main__ in the bootstrap library.zip.
    #  The frozen library.zip might have the loader prepended to it, but
    #  that gets overwritten here.
    bslib_path = dist.copy_to_bootstrap_env("library.zip")
    bslib = zipfile.PyZipFile(bslib_path,"w",zipfile.ZIP_STORED)
    cdate = (2000,1,1,0,0,0)
    bslib.writestr(zipfile.ZipInfo("__main__.pyc",cdate),maincode)
    bslib.writestr(zipfile.ZipInfo("esky/__init__.pyc",cdate),eskycode)
    bslib.writestr(zipfile.ZipInfo("esky/bootstrap.pyc",cdate),eskybscode)
    bslib.close()
    #  Copy any core dependencies
    for nm in os.listdir(dist.freeze_dir):
        if is_core_dependency(nm):
            dist.copy_to_bootstrap_env(nm)
    #  Copy the bbfreeze interpreter if necessary
    if f.include_py:
        if sys.platform == "win32":
            dist.copy_to_bootstrap_env("py.exe")
        else:
            dist.copy_to_bootstrap_env("py")
    #  Copy the loader program for each script.
    #  We explicitly strip the loader binaries, in case they were made
    #  by linking to the library.zip.
    for exe in dist.get_executables(rewrite=False):
        if not exe.include_in_bootstrap_env:
            continue
        exepath = dist.copy_to_bootstrap_env(exe.name)
        f.stripBinary(exepath)


#  On Windows, execv is flaky and expensive.  If the chainloader is the same
#  python version as the target exe, we can munge sys.path to bootstrap it
#  into the existing process.
_CUSTOM_WIN32_CHAINLOADER = """
_orig_chainload = _chainload
def _chainload(target_dir):
  mydir = dirname(sys.executable)
  pydll = "python%s%s.dll" % sys.version_info[:2]
  if not exists(pathjoin(target_dir,pydll)):
      _orig_chainload(target_dir)
  else:
      sys.bootstrap_executable = sys.executable
      sys.executable = pathjoin(target_dir,basename(sys.executable))
      sys.argv[0] = sys.executable
      for i in xrange(len(sys.path)):
          sys.path[i] = sys.path[i].replace(mydir,target_dir)
      import zipimport
      try:
          importer = zipimport.zipimporter(sys.path[0])
          code = importer.get_code("__main__")
      except ImportError:
          _orig_chainload(target_dir)
      else:
          sys.modules.pop("esky",None)
          sys.modules.pop("esky.bootstrap",None)
          try:
              exec code in {"__name__":"__main__"}
          except zipimport.ZipImportError, e:
              #  If it can't find the __main__{sys.executable} script,
              #  the user might be running from a backup exe file.
              #  Fall back to original chainloader to attempt workaround.
              if e.message.startswith("can't find module '__main__"):
                  _orig_chainload(target_dir)
              raise
          sys.exit(0)
"""



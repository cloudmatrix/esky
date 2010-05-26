#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.bdist_esky.f_cxfreeze:  bdist_esky support for cx_Freeze

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
import distutils
from glob import glob


import cx_Freeze
import cx_Freeze.hooks
INITNAME = "cx_Freeze__init__"

import esky
from esky.util import is_core_dependency


def freeze(dist):
    """Freeze the given distribution data using cx_Freeze."""
    includes = dist.includes
    excludes = dist.excludes
    options = dist.freezer_options
    #  Merge in any encludes/excludes given in freezer_options
    for inc in options.pop("includes",()):
        includes.append(inc)
    for exc in options.pop("excludes",()):
        excludes.append(exc)
    if "esky" not in includes and "esky" not in excludes:
        includes.append("esky")
    #  cx_Freeze doesn't seem to respect __path__ properly; hack it so
    #  that the required distutils modules are always found correctly.
    def load_distutils(finder,module):
        module.path = distutils.__path__ + module.path
        finder.IncludeModule("distutils.dist")
    cx_Freeze.hooks.load_distutils = load_distutils
    #  Build kwds arguments out of the given freezer opts.
    kwds = {}
    for (nm,val) in options.iteritems():
        kwds[_normalise_opt_name(nm)] = val
    kwds["includes"] = includes
    kwds["excludes"] = excludes
    kwds["targetDir"] = dist.freeze_dir
    #  Build an Executable object for each script.
    #  To include the esky startup code, we write each to a tempdir.
    executables = []
    for exe in dist.get_executables():
        base = None
        if exe.gui_only and sys.platform == "win32":
            base = "Win32GUI"
        executables.append(cx_Freeze.Executable(exe.script,base=base,targetName=exe.name,icon=exe.icon,**exe._kwds))
    #  Freeze up the executables
    f = cx_Freeze.Freezer(executables,**kwds)
    f.Freeze()
    #  Copy data files into the freeze dir
    for (src,dst) in dist.get_data_files():
        dst = os.path.join(dist.freeze_dir,dst)
        dstdir = os.path.dirname(dst)
        if not os.path.isdir(dstdir):
            dist.mkpath(dstdir)
        dist.copy_file(src,dst)
    #  Copy package data into the library.zip
    #  For now, this only works if there's a shared "library.zip" file.
    if f.createLibraryZip:
        lib = zipfile.ZipFile(os.path.join(dist.freeze_dir,"library.zip"),"a")
        for (src,arcnm) in dist.get_package_data():
            lib.write(src,arcnm)
        lib.close()
    else:
        for (src,arcnm) in dist.get_package_data():
            err = "use of package_data currently requires createLibraryZip=True"
            raise RuntimeError(err)
    #  Create the bootstrap code, using custom code if specified.
    code_source = [inspect.getsource(esky.bootstrap)]
    if sys.platform == "win32":
        code_source.append(_CUSTOM_WIN32_CHAINLOADER)
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
    maincode += marshal.dumps(compile(code_source,INITNAME+".py","exec"))
    #  Create code for a fake esky.bootstrap module
    eskycode = imp.get_magic() + struct.pack("<i",0)
    eskycode += marshal.dumps(compile("","esky/__init__.py","exec"))
    eskybscode = imp.get_magic() + struct.pack("<i",0)
    eskybscode += marshal.dumps(compile("","esky/bootstrap.py","exec"))
    #  Copy any core dependencies
    for nm in os.listdir(dist.freeze_dir):
        if is_core_dependency(nm):
            dist.copy_to_bootstrap_env(nm)
    #  Copy the loader program for each script into the bootstrap env, and
    #  append the bootstrapping code to it as a zipfile.
    for exe in dist.get_executables(rewrite=False):
        if not exe.include_in_bootstrap_env:
            continue
        exepath = dist.copy_to_bootstrap_env(exe.name)
        bslib = zipfile.PyZipFile(exepath,"a",zipfile.ZIP_STORED)
        cdate = (2000,1,1,0,0,0)
        bslib.writestr(zipfile.ZipInfo(INITNAME+".pyc",cdate),maincode)
        bslib.writestr(zipfile.ZipInfo("esky/__init__.pyc",cdate),eskycode)
        bslib.writestr(zipfile.ZipInfo("esky/bootstrap.pyc",cdate),eskybscode)
        bslib.close()


def _normalise_opt_name(nm):
    """Normalise option names for cx_Freeze.

    This allows people to specify options named like "opt-name" and have
    them converted to the "optName" format used internally by cx_Freeze.
    """
    bits = nm.split("-")
    for i in xrange(1,len(bits)):
        if bits[i]:
            bits[i] = bits[i][0].upper() + bits[i][1:]
    return "".join(bits)


#  On Windows, execv is flaky and expensive.  If the chainloader is the same
#  python version as the target exe, we can munge sys.path to bootstrap it
#  into the existing process.
_CUSTOM_WIN32_CHAINLOADER = """
_orig_chainload = _chainload
def _chainload(target_dir):
  mydir = dirname(sys.executable)
  pydll = "python%%s%%s.dll" %% sys.version_info[:2]
  if not exists(pathjoin(target_dir,pydll)):
      _orig_chainload(target_dir)
  else:
      sys.bootstrap_executable = sys.executable
      sys.executable = pathjoin(target_dir,basename(sys.executable))
      sys.argv[0] = sys.executable
      for i in xrange(len(sys.path)):
          sys.path[i] = sys.path[i].replace(mydir,target_dir)
      import zipimport
      for init_path in sys.path:
          try:
              importer = zipimport.zipimporter(init_path)
              code = importer.get_code("%s")
          except ImportError:
              pass
          else:
              sys.modules.pop("esky",None)
              sys.modules.pop("esky.bootstrap",None)
              #  Adjust various cxfreeze global vars
              global DIR_NAME, FILE_NAME, EXCLUSIVE_ZIP_FILE_NAME
              global SHARED_ZIP_FILE_NAME, INITSCRIPT_ZIP_FILE_NAME
              DIR_NAME = DIR_NAME.replace(mydir,target_dir)
              FILE_NAME = FILE_NAME.replace(mydir,target_dir)
              EXCLUSIVE_ZIP_FILE_NAME = EXCLUSIVE_ZIP_FILE_NAME.replace(mydir,target_dir)
              SHARED_ZIP_FILE_NAME = SHARED_ZIP_FILE_NAME.replace(mydir,target_dir)
              INITSCRIPT_ZIP_FILE_NAME = init_path
              try:
                  exec code in globals()
              except zipimport.ZipImportError, e:
                  #  If it can't find the __main__{sys.executable} script,
                  #  the user might be running from a backup exe file.
                  #  Fall back to original chainloader to attempt workaround.
                  if e.message.endswith("__main__'"):
                      _orig_chainload(target_dir)
                  raise
              sys.exit(0)
      else:
          _orig_chainload(target_dir)
""" % (INITNAME,)



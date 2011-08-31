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

if sys.platform == "win32":
    from esky import winres


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
    if "pypy" not in includes and "pypy" not in excludes:
        excludes.append("pypy")
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
    #  For win32 we include a special chainloader that can suck the selected
    #  version into the running process rather than spawn a new proc.
    code_source = ["__name__ = '__main__'"]
    esky_name = re.escape(dist.distribution.get_name())
    code_source.append("__esky_name__ = '%s'" % (esky_name,))
    code_source.append(inspect.getsource(esky.bootstrap))
    if dist.compile_bootstrap_exes:
        if sys.platform == "win32":
            #  The pypy-compiled bootstrap exe will try to load a python env
            #  into its own process and run this "take2" code to bootstrap.
            take2_code = code_source[1:]
            take2_code.append(_CUSTOM_WIN32_CHAINLOADER)
            take2_code.append(dist.get_bootstrap_code())
            take2_code = compile("\n".join(take2_code),"<string>","exec")
            take2_code = marshal.dumps(take2_code)
            clscript = "import marshal; "
            clscript += "exec marshal.loads(%r); " % (take2_code,)
            clscript = clscript.replace("%","%%")
            clscript += "chainload(\"%s\")"
            #  Here's the actual source for the compiled bootstrap exe.
            from esky.bdist_esky import pypy_libpython
            code_source.append(inspect.getsource(pypy_libpython))
            code_source.append("_PYPY_CHAINLOADER_SCRIPT = %r" % (clscript,))
            code_source.append(_CUSTOM_PYPY_CHAINLOADER)
        code_source.append(dist.get_bootstrap_code())
        code_source = "\n".join(code_source)
        for exe in dist.get_executables(normalise=False):
            if not exe.include_in_bootstrap_env:
                continue
            bsexe = dist.compile_to_bootstrap_exe(exe,code_source)
            if sys.platform == "win32":
                fexe = os.path.join(dist.freeze_dir,exe.name)
                winres.copy_safe_resources(fexe,bsexe)
        #  We may also need the bundled MSVCRT libs
        if sys.platform == "win32":
            for nm in os.listdir(dist.freeze_dir):
                if is_core_dependency(nm) and nm.startswith("Microsoft"):
                    dist.copy_to_bootstrap_env(nm)
    else:
        if sys.platform == "win32":
            code_source.append(_CUSTOM_WIN32_CHAINLOADER)
        code_source.append(dist.get_bootstrap_code())
        code_source.append("bootstrap()")
        code_source = "\n".join(code_source)
        #  For non-compiled bootstrap exe, store the bootstrapping code
        #  into the library.zip as __main__.
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
        if "fcntl" not in sys.builtin_module_names:
            for nm in os.listdir(dist.freeze_dir):
                if nm.startswith("fcntl"):
                    dist.copy_to_bootstrap_env(nm)
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
        for exe in dist.get_executables(normalise=False):
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
      verify(sys.executable)
      sys.prefix = sys.prefix.replace(mydir,target_dir)
      sys.argv[0] = sys.executable
      for i in xrange(len(sys.path)):
          sys.path[i] = sys.path[i].replace(mydir,target_dir)
      #  If we're in the bootstrap dir, try to chdir into the version dir.
      #  This is sometimes necessary for loading of DLLs by relative path.
      curdir = getcwd()
      if curdir == mydir:
          nt.chdir(target_dir)
      try:
          verify(sys.path[0])
          import zipimport
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

#  On Windows, execv is flaky and expensive.  Since the pypy-compiled bootstrap
#  exe doesn't have a python runtime, it needs to chainload the one from the
#  target version dir before trying to bootstrap in-process.
_CUSTOM_PYPY_CHAINLOADER = """

_orig_chainload = _chainload
def _chainload(target_dir):
  mydir = dirname(sys.executable)
  pydll = pathjoin(target_dir,"python%s%s.dll" % sys.version_info[:2])
  if not exists(pydll):
      _orig_chainload(target_dir)
  else:
      py = libpython(pydll)


      py.Set_NoSiteFlag(1)
      py.Set_FrozenFlag(1)
      py.Set_IgnoreEnvironmentFlag(1)

      py.SetPythonHome("")
      py.Initialize()
      # TODO: can't get this through pypy's type annotator.
      # going to fudge it in python instead :-)
      #py.Sys_SetArgv(list(sys.argv))
      syspath = dirname(py.GetProgramFullPath());
      syspath = syspath + "\\library.zip;" + syspath
      py.Sys_SetPath(syspath);
      #  Escape any double-quotes in sys.argv, so we can easily
      #  include it in a python-level string.
      new_argvs = []
      for arg in sys.argv:
          new_argvs.append('"' + arg.replace('"','\\"') + '"')
      new_argv = "[" + ",".join(new_argvs) + "]"
      py.Run_SimpleString("import sys; sys.argv = %s" % (new_argv,))
      py.Run_SimpleString("import sys; sys.frozen = 'bbfreeze'" % (new_argv,))
      globals = py.Dict_New()
      py.Dict_SetItemString(globals,"__builtins__",py.Eval_GetBuiltins())
      esc_target_dir_chars = []
      for c in target_dir:
          if c == "\\\\":
              esc_target_dir_chars.append("\\\\")
          esc_target_dir_chars.append(c)
      esc_target_dir = "".join(esc_target_dir_chars)
      script = _PYPY_CHAINLOADER_SCRIPT % (esc_target_dir,)
      py.Run_String(script,py.file_input,globals)
      py.Finalize()
      sys.exit(0)

"""

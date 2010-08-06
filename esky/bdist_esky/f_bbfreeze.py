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
    code_source = ["__name__ = '__main__'"]
    code_source.append(inspect.getsource(esky.bootstrap))
    if sys.platform == "win32":
        if dist.compile_bootstrap_exes:
            chainload = [code_source[0]]
            docstart = chainload[0].find('"""')
            docend = chainload[0].find('"""',docstart+1)
            chainload[0] = chainload[0][docend+3:].replace("\\","\\\\")
            chainload[0] = chainload[0].replace('"','\\"')
            chainload.append(_CUSTOM_WIN32_CHAINLOADER)
            chainload.append("chainload(target_dir)")
            chainload = "\n".join(chainload)
            code_source.append(_CUSTOM_WIN32_CHAINLOADER_PYPY % (chainload,))
        else:
            code_source.append(_CUSTOM_WIN32_CHAINLOADER)
    code_source.append("__esky_name__ = '%s'" % (dist.distribution.get_name(),))
    code_source.append(dist.get_bootstrap_code())
    code_source.append("if not __esky_compile_with_pypy__:")
    code_source.append("    bootstrap()")
    code_source = "\n".join(code_source)
    if dist.compile_bootstrap_exes:
        for exe in dist.get_executables(normalise=False):
            if not exe.include_in_bootstrap_env:
                continue
            dist.compile_to_bootstrap_exe(exe,code_source)
    else:
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


_CUSTOM_WIN32_CHAINLOADER_PYPY = """

Py_file_input = 257

from pypy.rlib import libffi
from pypy.rpython.lltypesystem import rffi, lltype

_CUSTOM_WIN32_CHAINLOADER = \"\"\"
%s
\"\"\"

class libpython:

    def __init__(self,library_path):
        self.lib = libffi.CDLL(library_path)

    def Initialize(self):
        impl = self.lib.getpointer("Py_Initialize",[],libffi.ffi_type_void)
        impl.call(lltype.Void)

    def Finalize(self):
        impl = self.lib.getpointer("Py_Finalize",[],libffi.ffi_type_void)
        impl.call(lltype.Void)

    def Err_Occurred(self):
        impl = self.lib.getpointer("PyErr_Occurred",[],libffi.ffi_type_pointer)
        return impl.call(rffi.VOIDP)

    def Err_PrintEx(self,set_sys_last_vars=1):
        impl = self.lib.getpointer("PyErr_PrintEx",[libffi.ffi_type_sint],libffi.ffi_type_void)
        impl.push_arg(set_sys_last_vars)
        return impl.call(lltype.Void)

    def _error(self):
        err = self.Err_Occurred()
        if err:
            self.Err_PrintEx()
            raise RuntimeError("an error occurred")

    def Run_SimpleString(self,string):
        impl = self.lib.getpointer("PyRun_SimpleString",[libffi.ffi_type_pointer],libffi.ffi_type_sint)
        buf = rffi.str2charp(string)
        impl.push_arg(buf)
        res = impl.call(rffi.INT)
        rffi.free_charp(buf)
        if res < 0:
            self._error()

    def Run_String(self,string,start,globals=None,locals=None):
        if globals is None:
            globals = 0
        if locals is None:
            locals = 0
        impl = self.lib.getpointer("PyRun_String",[libffi.ffi_type_pointer,libffi.ffi_type_sint,libffi.ffi_type_pointer,libffi.ffi_type_pointer],libffi.ffi_type_pointer)
        buf = rffi.str2charp(string)
        impl.push_arg(buf)
        impl.push_arg(start)
        impl.push_arg(globals)
        impl.push_arg(locals)
        res = impl.call(rffi.VOIDP)
        rffi.free_charp(buf)
        if not res:
            self._error()
        return res

    def GetProgramFullPath(self):
        impl = self.lib.getpointer("Py_GetProgramFullPath",[],libffi.ffi_type_pointer)
        return rffi.charp2str(impl.call(rffi.CCHARP))

    def SetPythonHome(self,path):
        impl = self.lib.getpointer("Py_SetPythonHome",[libffi.ffi_type_pointer],libffi.ffi_type_void)
        buf = rffi.str2charp(path)
        impl.push_arg(buf)
        impl.call(lltype.Void)
        rffi.free_charp(buf)

    # TODO: this seems to cause type errors during building
    def Sys_SetArgv(self,argv):
        impl = self.lib.getpointer("PySys_SetArgv",[libffi.ffi_type_sint,libffi.ffi_type_pointer],libffi.ffi_type_void)
        impl.push_arg(len(argv))
        buf = rffi.liststr2charpp(argv)
        impl.push_arg(rffi.cast(rffi.VOIDP,buf))
        impl.call(lltype.Void)
        rffi.free_charpp(buf)

    def Sys_SetPath(self,path):
        impl = self.lib.getpointer("PySys_SetPath",[libffi.ffi_type_pointer],libffi.ffi_type_void)
        buf = rffi.str2charp(path)
        impl.push_arg(buf)
        impl.call(lltype.Void)
        rffi.free_charp(buf)

    def Eval_GetBuiltins(self):
        impl = self.lib.getpointer("PyEval_GetBuiltins",[],libffi.ffi_type_pointer)
        d = impl.call(rffi.VOIDP)
        if not d:
            self._error()
        return d

    def Dict_New(self):
        impl = self.lib.getpointer("PyDict_New",[],libffi.ffi_type_pointer)
        d = impl.call(rffi.VOIDP)
        if not d:
            self._error()
        return d

    def Dict_SetItemString(self,d,key,value):
        impl = self.lib.getpointer("PyDict_SetItemString",[libffi.ffi_type_pointer,libffi.ffi_type_pointer,libffi.ffi_type_pointer],libffi.ffi_type_sint)
        impl.push_arg(d)
        buf = rffi.str2charp(key)
        impl.push_arg(buf)
        impl.push_arg(value)
        d = impl.call(rffi.INT)
        rffi.free_charp(buf)
        if d < 0:
            self._error()


_orig_chainload = _chainload
def _chainload(target_dir):
  mydir = dirname(sys.executable)
  pydll = "python%%s%%s.dll" %% sys.version_info[:2]
  if not exists(pathjoin(target_dir,pydll)):
      _orig_chainload(target_dir)
  else:
      py = libpython(pydll)

      #Py_NoSiteFlag = 1;
      #Py_FrozenFlag = 1;
      #Py_IgnoreEnvironmentFlag = 1;

      py.SetPythonHome("")
      py.Initialize()
      # TODO: can't get this through pypy's type annotator.
      # going to fudge it in python instead :-)
      #py.Sys_SetArgv(list(sys.argv))
      syspath = dirname(py.GetProgramFullPath());
      syspath = syspath + "\\library.zip;" + syspath
      py.Sys_SetPath(syspath);
      new_argvs = []
      for arg in sys.argv:
          new_argvs.append('"' + arg.replace('"','\\"') + '"')
      new_argv = "[" + ",".join(new_argvs) + "]"
      py.Run_SimpleString("import sys; sys.argv = %%s" %% (new_argv,))
      py.Run_SimpleString("import sys; sys.frozen = 'bbfreeze'" %% (new_argv,))
      globals = py.Dict_New()
      py.Dict_SetItemString(globals,"__builtins__",py.Eval_GetBuiltins())
      esc_target_dir_chars = []
      for c in target_dir:
          if c == "\\\\":
              esc_target_dir_chars.append("\\\\")
          esc_target_dir_chars.append(c)
      esc_target_dir = "".join(esc_target_dir_chars)
      script = "target_dir = '%%s'\\n\\n%%s" %% (esc_target_dir,_CUSTOM_WIN32_CHAINLOADER,)
      py.Run_String(script,Py_file_input,globals)
      py.Finalize()
      sys.exit(0)

"""

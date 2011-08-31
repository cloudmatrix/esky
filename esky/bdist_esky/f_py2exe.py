#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.bdist_esky.f_py2exe:  bdist_esky support for py2exe

"""

from __future__ import with_statement


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
import ctypes


from py2exe.build_exe import py2exe

import esky
from esky.util import is_core_dependency, ESKY_CONTROL_DIR
from esky import winres

try:
    import py2exe.mf as modulefinder
except ImportError:
    modulefinder = None

#  Hack to make win32com work seamlessly with py2exe
if modulefinder is not None:
  try:
    import win32com
    for p in win32com.__path__[1:]:
        modulefinder.AddPackagePath("win32com", p)
    for extra in ["win32com.shell"]: #,"win32com.mapi"
        __import__(extra)
        m = sys.modules[extra]
        for p in m.__path__[1:]:
           modulefinder.AddPackagePath(extra, p)
  except ImportError:
     pass


class custom_py2exe(py2exe): 
    """Custom py2exe command subclass.

    This py2exe command subclass incorporates some well-known py2exe "hacks"
    to make common third-party packages work better.
    """

    def create_modulefinder(self):
        mf = py2exe.create_modulefinder(self)
        self.__mf = mf
        return mf

    def build_manifest(self,target,template):
        (mfest,mid) = py2exe.build_manifest(self,target,template)
        #  Hack to get proper UI theme when freezing wxPython
        if mfest is not None:
            if "wx" in self.__mf.modules:
                mfest = mfest.replace("</assembly>","""
                    <dependency>
                      <dependentAssembly>
                        <assemblyIdentity
                         type="win32"
                         name="Microsoft.Windows.Common-Controls"
                         version="6.0.0.0"
                         processorArchitecture="*"
                         publicKeyToken="6595b64144ccf1df"
                         language="*" />
                      </dependentAssembly>
                   </dependency>
                 </assembly>""")
        return (mfest,mid)


def freeze(dist):
    """Freeze the given distribution data using py2exe."""
    includes = dist.includes
    excludes = dist.excludes
    options = dist.freezer_options
    #  Merge in any encludes/excludes given in freezer_options
    includes.append("esky")
    for inc in options.pop("includes",()):
        includes.append(inc)
    for exc in options.pop("excludes",()):
        excludes.append(exc)
    if "pypy" not in includes and "pypy" not in excludes:
        excludes.append("pypy")
    #  py2exe expects some arguments on the main distribution object.
    #  We handle data_files ourselves, so fake it out for py2exe.
    if getattr(dist.distribution,"console",None):
        msg = "don't call setup(console=[...]) with esky;"
        msg += " use setup(scripts=[...]) instead"
        raise RuntimeError(msg)
    if getattr(dist.distribution,"windows",None):
        msg = "don't call setup(windows=[...]) with esky;"
        msg += " use setup(scripts=[...]) instead"
        raise RuntimeError(msg)
    dist.distribution.console = []
    dist.distribution.windows = []
    my_data_files = dist.distribution.data_files
    dist.distribution.data_files = []
    for exe in dist.get_executables():
        #  Pass any executable kwds through to py2exe.
        #  We handle "icon" and "gui_only" ourselves.
        s = exe._kwds.copy()
        s["script"] = exe.script
        s["dest_base"] = exe.name[:-4]
        if exe.icon is not None and "icon_resources" not in s:
            s["icon_resources"] = [(1,exe.icon)]
        if exe.gui_only:
            dist.distribution.windows.append(s)
        else:
            dist.distribution.console.append(s)
    if "zipfile" in options:
        dist.distribution.zipfile = options.pop("zipfile")
    #  Create the py2exe cmd and adjust its options
    cmd = custom_py2exe(dist.distribution)
    cmd.includes = includes
    cmd.excludes = excludes
    if "bundle_files" in options:
        if options["bundle_files"] < 3 and dist.compile_bootstrap_exes:
             err = "can't compile bootstrap exes when bundle_files < 3"
             raise RuntimeError(err)
    for (nm,val) in options.iteritems():
        setattr(cmd,nm,val)
    cmd.dist_dir = dist.freeze_dir
    cmd.finalize_options()
    #  Actually run the freeze process
    cmd.run()
    #  Copy data files into the freeze dir
    dist.distribution.data_files = my_data_files
    for (src,dst) in dist.get_data_files():
        dst = os.path.join(dist.freeze_dir,dst)
        dstdir = os.path.dirname(dst)
        if not os.path.isdir(dstdir):
            dist.mkpath(dstdir)
        dist.copy_file(src,dst)
    #  Place a marker file so we know how it was frozen
    os.mkdir(os.path.join(dist.freeze_dir,ESKY_CONTROL_DIR))
    marker_file = os.path.join(ESKY_CONTROL_DIR,"f-py2exe-%d%d.txt")%sys.version_info[:2]
    open(os.path.join(dist.freeze_dir,marker_file),"w").close()
    #  Copy package data into the library.zip
    #  For now, we don't try to put package data into a bundled zipfile.
    dist_zipfile = dist.distribution.zipfile
    if dist_zipfile is None:
        for (src,arcnm) in dist.get_package_data():
            err = "zipfile=None can't be used with package_data (yet...)"
            raise RuntimeError(err)
    elif not cmd.skip_archive:
        lib = zipfile.ZipFile(os.path.join(dist.freeze_dir,dist_zipfile),"a")
        for (src,arcnm) in dist.get_package_data():
            lib.write(src,arcnm)
        lib.close()
    else:
        for (src,arcnm) in dist.get_package_data():
            lib = os.path.join(dist.freeze_dir,os.path.dirname(dist_zipfile))
            dest = os.path.join(lib, os.path.dirname(src))
            f = os.path.basename(src)
            if not os.path.isdir(dest):
                dist.mkpath(dest)
            dist.copy_file(src,os.path.join(dest, f))
    #  There's no need to copy library.zip into the bootstrap env, as the
    #  chainloader will run before py2exe goes looking for it.
    pass
    #  Create the bootstraping code, using custom code if specified.
    #  It gets stored as a marshalled list of code objects directly in the exe.
    esky_name = re.escape(dist.distribution.get_name())
    code_source = ["__esky_name__ = '%s'" % (esky_name,)]
    code_source.append(inspect.getsource(esky.bootstrap))
    if dist.compile_bootstrap_exes:
        from esky.bdist_esky import pypy_libpython
        from esky.bdist_esky import pypy_winres
        code_source.append(inspect.getsource(pypy_libpython))
        code_source.append(inspect.getsource(pypy_winres))
        code_source.append(_CUSTOM_PYPY_CHAINLOADER)
        code_source.append(dist.get_bootstrap_code())
        code_source = "\n".join(code_source)
        for exe in dist.get_executables(normalise=False):
            if not exe.include_in_bootstrap_env:
                continue
            fexe = os.path.join(dist.freeze_dir,exe.name)
            bsexe = dist.compile_to_bootstrap_exe(exe,code_source)
            winres.copy_safe_resources(fexe,bsexe)
        #  We may also need the bundled MSVCRT libs
        for nm in os.listdir(dist.freeze_dir):
            if is_core_dependency(nm) and nm.startswith("Microsoft"):
                dist.copy_to_bootstrap_env(nm)
    else:
        code_source.append(_FAKE_ESKY_BOOTSTRAP_MODULE)
        code_source.append(_CUSTOM_WIN32_CHAINLOADER)
        code_source.append(dist.get_bootstrap_code())
        code_source.append("bootstrap()")
        code_source = "\n".join(code_source)
        code = marshal.dumps([compile(code_source,"__main__.py","exec")])
        #  Copy any core dependencies into the bootstrap env.
        for nm in os.listdir(dist.freeze_dir):
            if is_core_dependency(nm):
                dist.copy_to_bootstrap_env(nm)
        #  Copy the loader program for each script into the bootstrap env.
        for exe in dist.get_executables(normalise=False):
            if not exe.include_in_bootstrap_env:
                continue
            exepath = dist.copy_to_bootstrap_env(exe.name)
            #  Read the py2exe metadata from the frozen exe.  We will
            #  need to duplicate some of these fields when to rewrite it.
            coderes = winres.load_resource(exepath,u"PYTHONSCRIPT",1,0)
            headsz = struct.calcsize("iiii")
            (magic,optmz,unbfrd,codesz) = struct.unpack("iiii",coderes[:headsz])
            assert magic == 0x78563412
            #  Insert the bootstrap code into the exe as a resource.
            #  This appears to have the happy side-effect of stripping any
            #  extra data from the end of the exe, which is exactly what we
            #  want when zipfile=None is specified; otherwise each bootstrap
            #  exe would also contain the whole bundled zipfile.
            coderes = struct.pack("iiii",
                         magic, # magic value used for integrity checking,
                         optmz, # optimization level to enable
                         unbfrd,  # whether to use unbuffered output
                         len(code),
                      ) + "\x00" + code + "\x00\x00"
            winres.add_resource(exepath,coderes,u"PYTHONSCRIPT",1,0)
        #  If the python dll hasn't been copied into the bootstrap env,
        #  make sure it's stored in each bootstrap dll as a resource.
        pydll = u"python%d%d.dll" % sys.version_info[:2]
        if not os.path.exists(os.path.join(dist.bootstrap_dir,pydll)):
            buf = ctypes.create_string_buffer(3000)
            GetModuleFileNameA = ctypes.windll.kernel32.GetModuleFileNameA
            if not GetModuleFileNameA(sys.dllhandle,ctypes.byref(buf),3000):
                raise ctypes.WinError()
            with open(buf.value,"rb") as f:
                pydll_bytes = f.read()
            for exe in dist.get_executables(normalise=False):
                if not exe.include_in_bootstrap_env:
                    continue
                exepath = os.path.join(dist.bootstrap_dir,exe.name)
                try:
                    winres.load_resource(exepath,pydll.upper(),1,0)
                except EnvironmentError:
                    winres.add_resource(exepath,pydll_bytes,pydll.upper(),1,0)

#  Code to fake out any bootstrappers that try to import from esky.
_FAKE_ESKY_BOOTSTRAP_MODULE = """
class __fake:
  __all__ = ()
sys.modules["esky"] = __fake()
sys.modules["esky.bootstrap"] = __fake()
"""


#  On Windows, execv is flaky and expensive.  If the chainloader is the same
#  python version as the target exe, we can munge sys.path to bootstrap it
#  into the existing process.
#
#  We need to read the script to execute as a resource from the exe, so this
#  only works if we can bootstrap a working ctypes module.  We then insert
#  the source code from esky.winres.load_resource directly into this function.
#
_CUSTOM_WIN32_CHAINLOADER = """

_orig_chainload = _chainload

def _chainload(target_dir):
  # Be careful to escape percent-sign, this gets interpolated below
  marker_file = pathjoin(ESKY_CONTROL_DIR,"f-py2exe-%%d%%d.txt")%%sys.version_info[:2]
  pydll = "python%%s%%s.dll" %% sys.version_info[:2]
  mydir = dirname(sys.executable)
  #  Check that the target directory is the same version of python as this
  #  bootstrapping script.  If not, we can't chainload it in-process.
  if not exists(pathjoin(target_dir,marker_file)):
      return _orig_chainload(target_dir)
  #  Check whether the target directory contains unbundled C extensions.
  #  These require a physical python dll on disk next to the running
  #  executable, so we must have such a dll in order to chainload.
  #  bootstrapping script.  If not, we can't chainload it in-process.
  for nm in listdir(target_dir):
      if nm == pydll:
          continue
      if nm.lower().startswith("msvcr"):
          continue
      if nm.lower().endswith(".pyd") or nm.lower().endswith(".dll"):
          #  The freeze dir contains unbundled C extensions.
          if not exists(pathjoin(mydir,pydll)):
              return _orig_chainload(target_dir)
          else:
               break
  # Munge the environment to pretend we're in the target dir.
  # This will let us load modules from inside it.
  # If we fail for whatever reason, we can't chainload in-process.
  try:
      import nt
  except ImportError:
      return _orig_chainload(target_dir)
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
  #  Use the library.zip from the version dir.
  #  It should already be in sys.path from the above env mangling,
  #  but you never know...
  libfile = pathjoin(target_dir,"library.zip")
  if libfile not in sys.path:
      if exists(libfile):
          sys.path.append(libfile)
      else:
          sys.path.append(target_dir)
  # Try to import the modules we need for bootstrapping.
  # If we fail for whatever reason, we can't chainload in-process.
  try:
      import zipextimporter; zipextimporter.install()
  except ImportError:
      pass
  try:
      import ctypes
      import struct
      import marshal
      import msvcrt
  except ImportError:
      return _orig_chainload(target_dir)
  # The source for esky.winres.load_resource gets inserted below.
  # This allows us to grab the code out of the frozen version exe.
  from ctypes import c_char, POINTER
  k32 = ctypes.windll.kernel32
  LOAD_LIBRARY_AS_DATAFILE = 0x00000002
  _DEFAULT_RESLANG = 1033
  %s
  # Great, now we magically have the load_resource function :-)
  try:
      data = load_resource(sys.executable,u"PYTHONSCRIPT",1,0)
  except EnvironmentError:
      #  This will trigger if sys.executable doesn't exist.
      #  Falling back to the original chainloader will account for
      #  the unlikely case where sys.executable is a backup file.
      return _orig_chainload(target_dir)
  else:
      sys.modules.pop("esky",None)
      sys.modules.pop("esky.bootstrap",None)
      headsz = struct.calcsize("iiii")
      (magic,optmz,unbfrd,codesz) = struct.unpack("iiii",data[:headsz])
      assert magic == 0x78563412
      # Set up the environment requested by "optimized" flag.
      # Currently "unbuffered" is not supported at run-time since I
      # haven't figured out the necessary incantations.
      try:
          opt_var = ctypes.c_int.in_dll(ctypes.pythonapi,"Py_OptimizeFlag")
          opt_var.value = optmz
      except ValueError:
          pass
      # Skip over the archive name to find start of code
      codestart = headsz
      while data[codestart] != "\\0":
          codestart += 1
      codestart += 1
      codeend = codestart + codesz
      codelist = marshal.loads(data[codestart:codeend])
      # Execute all code in the context of __main__ module.
      d_locals = d_globals = sys.modules["__main__"].__dict__
      d_locals["__name__"] = "__main__"
      for code in codelist:
          exec code in d_globals, d_locals
      raise SystemExit(0)
""" % (inspect.getsource(winres.load_resource).replace("\n","\n"+" "*4),)


#  On Windows, execv is flaky and expensive.  Since the pypy-compiled bootstrap
#  exe doesn't have a python runtime, it needs to chainload the one from the
#  target version dir before trying to bootstrap in-process.
_CUSTOM_PYPY_CHAINLOADER = """

import nt
from pypy.rlib.rstruct.runpack import runpack

import time;

_orig_chainload = _chainload

def _chainload(target_dir):
  mydir = dirname(sys.executable)
  pydll = pathjoin(target_dir,"python%s%s.dll" % sys.version_info[:2])
  if not exists(pydll):
      return _orig_chainload(target_dir)
  else:

      #  Munge the environment for DLL loading purposes
      try:
          environ["PATH"] = environ["PATH"] + ";" + target_dir
      except KeyError:
          environ["PATH"] = target_dir

      #  Get the target python env up and running
      verify(pydll)
      py = libpython(pydll)
      py.Set_NoSiteFlag(1)
      py.Set_FrozenFlag(1)
      py.Set_IgnoreEnvironmentFlag(1)
      py.SetPythonHome("")
      py.Initialize()

      #  Extract the marshalled code data from the target executable,
      #  store it into a python string object.
      target_exe = pathjoin(target_dir,basename(sys.executable))
      verify(target_exe)
      try:
          py_data = load_resource_pystr(py,target_exe,"PYTHONSCRIPT",1,0)
      except EnvironmentError:
          return _orig_chainload(target_dir)
      data = py.String_AsString(py_data)
      headsz = 16  # <-- struct.calcsize("iiii")
      headdata = rffi.charpsize2str(rffi.cast(rffi.CCHARP,data),headsz)
      (magic,optmz,unbfrd,codesz) = runpack("iiii",headdata)
      assert magic == 0x78563412
      # skip over the archive name to find start of code
      codestart = headsz
      while data[codestart] != "\\0":
          codestart += 1
      codestart += 1
      codeend = codestart + codesz
      assert codeend > 0

      #  Tweak the python env according to the py2exe frozen metadata
      py.Set_OptimizeFlag(optmz)
      # TODO: set up buffering
      # If you can decide on buffered/unbuffered before loading up
      # the python runtime, this can be done by just setting the
      # PYTHONUNBUFFERED environment variable.  If not, we have to
      # do it ourselves like this:
      #if unbfrd:
      #     setmode(0,nt.O_BINARY)
      #     setmode(1,nt.O_BINARY)
      #     setvbuf(stdin,NULL,4,512)
      #     setvbuf(stdout,NULL,4,512)
      #     setvbuf(stderr,NULL,4,512)

      #  Preted the python env is running from within the frozen executable
      syspath = "%s;%s\\library.zip;%s" % (target_exe,target_dir,target_dir,)
      py.Sys_SetPath(syspath);
      sysmod = py.Import_ImportModule("sys")
      sysargv = py.List_New(len(sys.argv))
      for i in xrange(len(sys.argv)):
          py.List_SetItem(sysargv,i,py.String_FromString(sys.argv[i]))
      py.Object_SetAttrString(sysmod,"argv",sysargv)
      py.Object_SetAttrString(sysmod,"frozen",py.String_FromString("py2exe"))
      py.Object_SetAttrString(sysmod,"executable",py.String_FromString(target_exe))
      py.Object_SetAttrString(sysmod,"bootstrap_executable",py.String_FromString(sys.executable))
      py.Object_SetAttrString(sysmod,"prefix",py.String_FromString(dirname(target_exe)))

      curdir = getcwd()
      if curdir == mydir:
          nt.chdir(target_dir)

      #  Execute the marshalled list of code objects
      globals = py.Dict_New()
      py.Dict_SetItemString(globals,"__builtins__",py.Eval_GetBuiltins())
      py.Dict_SetItemString(globals,"FROZEN_DATA",py_data)
      runcode =  "FROZEN_DATA = FROZEN_DATA[%d:%d]\\n" % (codestart,codeend,)
      runcode +=  "import sys\\n"
      runcode +=  "import marshal\\n"
      runcode += "d_locals = d_globals = sys.modules['__main__'].__dict__\\n"
      runcode += "d_locals['__name__'] = '__main__'\\n"
      runcode += "for code in marshal.loads(FROZEN_DATA):\\n"
      runcode += "  exec code in d_globals, d_locals\\n"
      py.Run_String(runcode,py.file_input,globals)

      #  Clean up after execution.
      py.Finalize()
      sys.exit(0)

"""



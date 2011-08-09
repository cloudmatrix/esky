"""

  esky.bdist_esky.pypyc:  support for compiling bootstrap exes with PyPy


This module provides the supporting code to compile bootstrapping exes with
PyPy.  In theory, this should provide for faster startup and less resource
usage than building the bootstrap exes out of the frozen application stubs.

"""

from __future__ import with_statement

import os
import sys

import pypy.translator.goal.translate

try:
    import pypy.rlib.clibffi
except (ImportError,AttributeError,), e:
    msg = "Compiling bootstrap exes requires PyPy v1.5 or later"
    msg += " [error: %s]" % (e,)
    raise ImportError(msg)


def compile_rpython(infile,outfile,gui_only=False,static_msvcrt=False):
    """Compile the given RPython input file to executable output file."""
    orig_argv = sys.argv[:]
    try:
        if sys.platform == "win32":
            pypy.translator.platform.host.gui_only = gui_only
        sys.argv[0] = sys.executable
        sys.argv[1:] = ["--output",outfile,"--batch","--gc=ref",]
        sys.argv.append(infile)
        pypy.translator.goal.translate.main()
    finally:
        sys.argv = orig_argv



#  For win32, we need some fancy features not provided by the normal
#  PyPy compiler.  Fortunately we can hack them in.
#
if sys.platform == "win32":
  import pypy.translator.platform.windows
  class CustomWin32Platform(pypy.translator.platform.windows.MsvcPlatform):
      """Custom PyPy platform object with fancy windows features.

      This platform knows how to do two things that native PyPy cannot -
      build a gui-only executable, and statically link the C runtime.
      Unfortunately there's a fair amount of monkey-patchery involved.
      """

      gui_only = False
      static_msvcrt = False

      def _is_main_srcfile(self,filename):
          if "platcheck" in filename:
              return True
          if "implement_1" in filename:
              return True
          return False

      def _compile_c_file(self,cc,cfile,compile_args):
          if self.gui_only:
              #  Add stub code for WinMain to gui-only compiles.
              if self._is_main_srcfile(str(cfile)):
                  with open(str(cfile),"r+b") as f:
                      data = f.read()
                      f.seek(0)
                      f.write(WINMAIN_STUB)
                      f.write(data)
          return super(CustomWin32Platform,self)._compile_c_file(cc,cfile,compile_args)

      def _link(self,cc,ofiles,link_args,standalone,exe_name):
          #  Link against windows subsystem if gui-only is specified.
          if self.gui_only:
              link_args.append("/subsystem:windows")
          #  Choose whether to link crt statically or dynamically.
          if not self.static_msvcrt:
              if "/MT" in self.cflags:
                  self.cflags.remove("/MT")
              if "/MD" not in self.cflags:
                  self.cflags.append("/MD")
          else:
              if "/MD" in self.cflags:
                  self.cflags.remove("/MD")
              if "/MT" not in self.cflags:
                  self.cflags.append("/MT")
              #  Static linking means no manifest is generated.
              #  Create a fake one so PyPy doesn't get confused.
              if self.version >= 80:
                  ofile = ofiles[-1]
                  manifest = str(ofile.dirpath().join(ofile.purebasename))
                  manifest += '.manifest'
                  with open(manifest,"w") as mf:
                      mf.write(DUMMY_MANIFEST)
          return super(CustomWin32Platform,self)._link(cc,ofiles,link_args,standalone,exe_name)

      def _finish_linking(self,ofiles,*args,**kwds):
          return super(CustomWin32Platform,self)._finish_linking(ofiles,*args,**kwds)

      #  Ugh.
      #  Trick pypy into letting us mix this with other platform objects.
      #  I should probably check that it's an MsvcPlatform...
      def __eq__(self, other):
          return True


  pypy.translator.platform.platform = CustomWin32Platform()
  pypy.translator.platform.host = pypy.translator.platform.platform
  pypy.translator.platform.host_factory = lambda *a: pypy.translator.platform.platform




WINMAIN_STUB = """
#ifndef PYPY_NOT_MAIN_FILE
#ifndef WIN32_LEAN_AND_MEAN

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdlib.h>

int WINAPI WinMain(HINSTANCE hInstance,HINSTANCE hPrevInstance,
                   LPWSTR lpCmdLine,int nCmdShow) {
    return main(__argc, __argv);
}

#endif
#endif
"""

DUMMY_MANIFEST =  """
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
</assembly>
"""

if __name__ == "__main__":
    import optparse 
    parser = optparse.OptionParser()
    parser.add_option("-g","--gui-only",action="store_true")
    parser.add_option("","--static-msvcrt",action="store_true")
    (opts,args) = parser.parse_args()
    if len(args) == 0:
        raise RuntimeError("no input file specified")
    if len(args) == 1:
        outfile = os.path.basename(args[0]).rsplit(".",1)[0] + "-c"
        if sys.platform == "win32":
            outfile += ".exe"
        outfile = os.path.join(os.path.dirname(args[0]),outfile)
        args.append(outfile)
    compile_rpython(args[0],args[1],opts.gui_only,opts.static_msvcrt)




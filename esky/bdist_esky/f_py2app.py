#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.bdist_esky.f_py2app:  bdist_esky support for py2app

"""

from __future__ import with_statement


import os
import re
import sys
import imp
import time
import errno
import zipfile
import shutil
import tempfile
import inspect
from StringIO import StringIO


from py2app.build_app import py2app, get_zipfile, Target

import esky
from esky.util import is_core_dependency, create_zipfile


def freeze(dist):
    """Freeze the given distribution data using py2app."""
    includes = dist.includes
    excludes = dist.excludes
    options = dist.freezer_options
    #  Merge in any includes/excludes given in freezer_options
    includes.append("esky")
    for inc in options.pop("includes",()):
        includes.append(inc)
    for exc in options.pop("excludes",()):
        excludes.append(exc)
    if "pypy" not in includes and "pypy" not in excludes:
        excludes.append("pypy")
    options["includes"] = includes
    options["excludes"] = excludes
    # py2app can't simultaneously freeze multiple scripts.
    # We do a separate freeze of each then merge them together.
    # The control info (name, icon, etc) for the app will be taken from
    # the first script in the list.
    exes = list(dist.get_executables())
    if not exes:
        raise RuntimeError("no scripts specified")
    cmd = _make_py2app_cmd(dist.freeze_dir,dist.distribution,options,exes[0])
    cmd.run()
    for exe in exes[1:]:
        tempdir = tempfile.mkdtemp()
        try:
            cmd = _make_py2app_cmd(tempdir,dist.distribution,options,exe)
            cmd.run()
            _merge_dir(tempdir,dist.freeze_dir)
        finally:
            shutil.rmtree(tempdir)
    #  Remove any .pyc files with a corresponding .py file.
    #  This helps avoid timestamp changes that might interfere with
    #  the generation of useful patches between versions.
    appnm = dist.distribution.get_name()+".app"
    app_dir = os.path.join(dist.freeze_dir,appnm)
    resdir = os.path.join(app_dir,"Contents/Resources")
    for (dirnm,_,filenms) in os.walk(resdir):
        for nm in filenms:
            if nm.endswith(".pyc"):
                pyfile = os.path.join(dirnm,nm[:-1])
                if os.path.exists(pyfile):
                    os.unlink(pyfile+"c")
            if nm.endswith(".pyo"):
                pyfile = os.path.join(dirnm,nm[:-1])
                if os.path.exists(pyfile):
                    os.unlink(pyfile+"o")
    #  Copy data files into the freeze dir
    for (src,dst) in dist.get_data_files():
        dst = os.path.join(app_dir,"Contents","Resources",dst)
        dstdir = os.path.dirname(dst)
        if not os.path.isdir(dstdir):
            dist.mkpath(dstdir)
        dist.copy_file(src,dst)
    #  Copy package data into site-packages.zip
    zfpath = os.path.join(cmd.lib_dir,get_zipfile(dist.distribution))
    lib = zipfile.ZipFile(zfpath,"a")
    for (src,arcnm) in dist.get_package_data():
        lib.write(src,arcnm)
    lib.close()
    #  Create the bootstraping code, using custom code if specified.
    esky_name = re.escape(dist.distribution.get_name())
    code_source = ["__esky_name__ = '%s'" % (esky_name,)]
    code_source.append(inspect.getsource(esky.bootstrap))
    if not dist.compile_bootstrap_exes:
        code_source.append(_FAKE_ESKY_BOOTSTRAP_MODULE)
        code_source.append(_EXTRA_BOOTSTRAP_CODE)
    code_source.append(dist.get_bootstrap_code())
    code_source.append("if not __rpython__:")
    code_source.append("    bootstrap()")
    code_source = "\n".join(code_source)
    def copy_to_bootstrap_env(src,dst=None):
        if dst is None:
            dst = src
        src = os.path.join(appnm,src)
        dist.copy_to_bootstrap_env(src,dst)
    if dist.compile_bootstrap_exes:
        for exe in dist.get_executables(normalise=False):
            if not exe.include_in_bootstrap_env:
                continue
            relpath = os.path.join("Contents","MacOS",exe.name)
            dist.compile_to_bootstrap_exe(exe,code_source,relpath)
    else:
        #  Copy the core dependencies into the bootstrap env.
        pydir = "python%d.%d" % sys.version_info[:2]
        for nm in ("Python.framework","lib"+pydir+".dylib",):
            try:
                copy_to_bootstrap_env("Contents/Frameworks/" + nm)
            except Exception, e:
                #  Distutils does its own crazy exception-raising which I
                #  have no interest in examining right now.  Eventually this
                #  guard will be more conservative.
                pass
        copy_to_bootstrap_env("Contents/Resources/include")
        copy_to_bootstrap_env("Contents/Resources/lib/"+pydir+"/config")
        if "fcntl" not in sys.builtin_module_names:
            dynload = "Contents/Resources/lib/"+pydir+"/lib-dynload"
            for nm in os.listdir(os.path.join(app_dir,dynload)):
                if nm.startswith("fcntl"):
                    copy_to_bootstrap_env(os.path.join(dynload,nm))
        copy_to_bootstrap_env("Contents/Resources/__error__.sh")
        copy_to_bootstrap_env("Contents/Resources/__boot__.py")
        copy_to_bootstrap_env("Contents/Resources/site.py")
        #  Copy the bootstrapping code into the __boot__.py file.
        bsdir = dist.bootstrap_dir
        with open(bsdir+"/Contents/Resources/__boot__.py","wt") as f:
            f.write(code_source)
        #  Clear site.py in the bootstrap dir, it doesn't do anything useful.
        with open(bsdir+"/Contents/Resources/site.py","wt") as f:
            f.write("")
        #  Copy the loader program for each script into the bootstrap env.
        copy_to_bootstrap_env("Contents/MacOS/python")
        for exe in dist.get_executables(normalise=False):
            if not exe.include_in_bootstrap_env:
                continue
            exepath = copy_to_bootstrap_env("Contents/MacOS/"+exe.name)
    #  Copy non-python resources (e.g. icons etc) into the bootstrap dir
    copy_to_bootstrap_env("Contents/Info.plist")
    copy_to_bootstrap_env("Contents/PkgInfo")
    with open(os.path.join(app_dir,"Contents","Info.plist"),"rt") as f:
        infotxt = f.read()
    for nm in os.listdir(os.path.join(app_dir,"Contents","Resources")):
        if "<string>%s</string>" % (nm,) in infotxt:
            copy_to_bootstrap_env("Contents/Resources/"+nm)



def zipit(dist,bsdir,zfname):
    """Create the final zipfile of the esky.

    We customize this process for py2app, so that the zipfile contains a
    toplevel "<appname>.app" directory.  This allows users to just extract
    the zipfile and have a proper application all set up and working.
    """
    def get_arcname(fpath):
        return os.path.join(dist.distribution.get_name()+".app",fpath)
    return create_zipfile(bsdir,zfname,get_arcname,compress=True)


def _make_py2app_cmd(dist_dir,distribution,options,exe):
    cmd = py2app(distribution)
    for (nm,val) in options.iteritems():
        setattr(cmd,nm,val)
    cmd.dist_dir = dist_dir
    cmd.app = [Target(script=exe.script,dest_base=exe.name,
                      prescripts=[StringIO(_EXE_PRESCRIPT_CODE)])]
    cmd.finalize_options()
    cmd.plist["CFBundleExecutable"] = exe.name
    old_run = cmd.run
    def new_run():
        #  py2app munges the environment in ways that break things.
        old_deployment_target = os.environ.get("MACOSX_DEPLOYMENT_TARGET",None)
        old_run()
        if old_deployment_target is None:
            os.environ.pop("MACOSX_DEPLOYMENT_TARGET",None)
        else:
            os.environ["MACOSX_DEPLOYMENT_TARGET"] = old_deployment_target
        #  We need to script file to have the same name as the exe, which
        #  it won't if they have changed it explicitly.
        resdir = os.path.join(dist_dir,distribution.get_name()+".app","Contents/Resources")
        scriptf = os.path.join(resdir,exe.name+".py")
        if not os.path.exists(scriptf):
           old_scriptf = os.path.basename(exe.script)
           old_scriptf = os.path.join(resdir,old_scriptf)
           shutil.move(old_scriptf,scriptf)
    cmd.run = new_run
    return cmd


def _merge_dir(src,dst):
    if not os.path.isdir(dst):
        os.makedirs(dst)
    for nm in os.listdir(src):
        srcnm = os.path.join(src,nm)
        dstnm = os.path.join(dst,nm)
        if os.path.isdir(srcnm):
            _merge_dir(srcnm,dstnm)
        else:
            if not os.path.exists(dstnm):
               shutil.copy2(srcnm,dstnm)
        

#  Code to fake out any bootstrappers that try to import from esky.
_FAKE_ESKY_BOOTSTRAP_MODULE = """
class __fake:
  __all__ = ()
sys.modules["esky"] = __fake()
sys.modules["esky.bootstrap"] = __fake()
"""

#  py2app goes out of its way to set sys.executable to a normal python
#  interpreter, which will break the standard bootstrapping code.
#  Get the original value back.
_EXTRA_BOOTSTRAP_CODE = """
from posix import environ
sys.executable = environ["EXECUTABLEPATH"]
sys.argv[0] = environ["ARGVZERO"]
"""


#  py2app isn't designed for freezing multiple exes, so its standard
#  bootstrap code runs a fixed script.  This code gets inserted into the
#  bootstrap code to inspect the environment and find the actual script
#  to be run.
_EXE_PRESCRIPT_CODE = """
import os
import sys
scriptnm = os.path.basename(os.environ["EXECUTABLEPATH"])
_run(scriptnm + ".py")
sys.exit(0)
"""


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
    #  Copy the core dependencies into the bootstrap env.
    pydir = "python%d.%d" % sys.version_info[:2]
    def copy_to_bootstrap_env(src,dst=None):
        if dst is None:
            dst = src
        src = os.path.join(appnm,src)
        dist.copy_to_bootstrap_env(src,dst)
    copy_to_bootstrap_env("Contents/Info.plist")
    copy_to_bootstrap_env("Contents/PkgInfo")
    copy_to_bootstrap_env("Contents/Frameworks/Python.framework")
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
    #  Copy any other mentioned files (icons etc) into the bootstrap env
    with open(os.path.join(app_dir,"Contents","Info.plist"),"rt") as f:
        infotxt = f .read()
    for nm in os.listdir(os.path.join(app_dir,"Contents","Resources")):
        if nm in infotxt:
            copy_to_bootstrap_env("Contents/Resources/"+nm)
    #  Create the bootstraping code, using custom code if specified.
    #  It gets stored as plain python code in Contents/Resources/__boot__.py
    code_source = [inspect.getsource(esky.bootstrap)]
    code_source.append(_FAKE_ESKY_BOOTSTRAP_MODULE)
    code_source.append(_EXTRA_BOOTSTRAP_CODE)
    code_source.append("__esky_name__ = '%s'" % (dist.distribution.get_name(),))
    if dist.bootstrap_code is not None:
        code_source.append(dist.bootstrap_code)
        code_source.append("raise RuntimeError('didnt chainload')")
    elif dist.bootstrap_module is not None:
        bsmodule = __import__(dist.bootstrap_module)
        for submod in dist.bootstrap_module.split(".")[1:]:
            bsmodule = getattr(bsmodule,submod)
        code_source.append(inspect.getsource(bsmodule))
        code_source.append("raise RuntimeError('didnt chainload')")
    else:
        code_source.append("bootstrap()")
    code_source = "\n".join(code_source)
    with open(dist.bootstrap_dir+"/Contents/Resources/__boot__.py","wt") as f:
        f.write("".join(code_source))
    with open(dist.bootstrap_dir+"/Contents/Resources/site.py","wt") as f:
        f.write("")
    # TODO: copy icons and other required resources
    #  Copy the loader program for each script into the bootstrap env.
    copy_to_bootstrap_env("Contents/MacOS/python")
    for exe in dist.get_executables():
        if not exe.include_in_bootstrap_env:
            continue
        exepath = copy_to_bootstrap_env("Contents/MacOS/"+exe.name)


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
        old_run()
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


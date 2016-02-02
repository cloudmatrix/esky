#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.bdist_esky.f_py2app:  bdist_esky support for py2app

"""

from __future__ import with_statement
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import *

import os
import sys
import imp
import zipfile
import shutil
import inspect
import struct
import marshal

from py2app.build_app import py2app, get_zipfile, Target

import esky
from esky.util import create_zipfile


def freeze(dist):
    """Freeze the given distribution data using py2app."""
    includes = dist.includes
    excludes = dist.excludes
    options = dist.freezer_options
    #  Merge in any includes/excludes given in freezer_options
    includes.append("esky")
    for inc in options.pop("includes", ()):
        includes.append(inc)
    for exc in options.pop("excludes", ()):
        excludes.append(exc)
    if "pypy" not in includes and "pypy" not in excludes:
        excludes.append("pypy")
    options["includes"] = includes
    options["excludes"] = excludes
    # The control info (name, icon, etc) for the app will be taken from
    # the first script in the list.  Subsequent scripts will be passed
    # as the extra_scripts argument.
    exes = list(dist.get_executables())
    if not exes:
        raise RuntimeError("no scripts specified")
    cmd = _make_py2app_cmd(dist.freeze_dir, dist.distribution, options, exes)
    cmd.run()
    #  Remove any .pyc files with a corresponding .py file.
    #  This helps avoid timestamp changes that might interfere with
    #  the generation of useful patches between versions.
    appnm = dist.distribution.get_name() + ".app"
    app_dir = os.path.join(dist.freeze_dir, appnm)
    resdir = os.path.join(app_dir, "Contents/Resources")
    for (dirnm, _, filenms) in os.walk(resdir):
        for nm in filenms:
            if nm.endswith(".pyc"):
                pyfile = os.path.join(dirnm, nm[:-1])
                if os.path.exists(pyfile):
                    os.unlink(pyfile + "c")
            if nm.endswith(".pyo"):
                pyfile = os.path.join(dirnm, nm[:-1])
                if os.path.exists(pyfile):
                    os.unlink(pyfile + "o")
    #  Copy data files into the freeze dir
    for (src, dst) in dist.get_data_files():
        dst = os.path.join(app_dir, "Contents", "Resources", dst)
        dstdir = os.path.dirname(dst)
        if not os.path.isdir(dstdir):
            dist.mkpath(dstdir)
        dist.copy_file(src, dst)
    #  Copy package data into site-packages.zip
    zfpath = os.path.join(cmd.lib_dir, get_zipfile(dist.distribution))
    lib = zipfile.ZipFile(zfpath, "a")
    for (src, arcnm) in dist.get_package_data():
        lib.write(src, arcnm)
    lib.close()
    #  Create the bootstraping code, using custom code if specified.
    esky_name = dist.distribution.get_name()
    code_source = ["__esky_name__ = %r" % (esky_name, )]
    code_source.append(inspect.getsource(esky.bootstrap))
    if not dist.compile_bootstrap_exes:
        code_source.append(_FAKE_ESKY_BOOTSTRAP_MODULE)
        code_source.append(_EXTRA_BOOTSTRAP_CODE)
    code_source.append(dist.get_bootstrap_code())
    code_source.append("if not __rpython__:")
    code_source.append("    bootstrap()")
    code_source = "\n".join(code_source)

    def copy_to_bootstrap_env(src, dst=None):
        if dst is None:
            dst = src
        src = os.path.join(appnm, src)
        dist.copy_to_bootstrap_env(src, dst)

    if dist.compile_bootstrap_exes:
        for exe in dist.get_executables(normalise=False):
            if not exe.include_in_bootstrap_env:
                continue
            relpath = os.path.join("Contents", "MacOS", exe.name)
            dist.compile_to_bootstrap_exe(exe, code_source, relpath)
    else:
        #  Copy the core dependencies into the bootstrap env.
        pydir = "python%d.%d" % sys.version_info[:2]
        for nm in ("Python.framework", "lib" + pydir + ".dylib", ):
            try:
                copy_to_bootstrap_env("Contents/Frameworks/" + nm)
            except Exception as e:
                #  Distutils does its own crazy exception-raising which I
                #  have no interest in examining right now.  Eventually this
                #  guard will be more conservative.
                pass
        copy_to_bootstrap_env("Contents/Resources/include")
        if sys.version_info[:2] < (3, 3):
            copy_to_bootstrap_env("Contents/Resources/lib/" + pydir +
                                  "/config")
        else:
            copy_to_bootstrap_env(
                "Contents/Resources/lib/" +
                pydir +
                "/config-%d.%dm" %
                sys.version_info[
                    :2])

        if "fcntl" not in sys.builtin_module_names:
            dynload = "Contents/Resources/lib/" + pydir + "/lib-dynload"
            for nm in os.listdir(os.path.join(app_dir, dynload)):
                if nm.startswith("fcntl"):
                    copy_to_bootstrap_env(os.path.join(dynload, nm))
        copy_to_bootstrap_env("Contents/Resources/__error__.sh")
        # Copy site.py/site.pyc into the boostrap env, then zero them out.
        bsdir = dist.bootstrap_dir
        if os.path.exists(os.path.join(app_dir, "Contents/Resources/site.py")):
            copy_to_bootstrap_env("Contents/Resources/site.py")
            with open(bsdir + "/Contents/Resources/site.py", "wt") as f:
                pass
        if os.path.exists(os.path.join(app_dir,
                                       "Contents/Resources/site.pyc")):
            copy_to_bootstrap_env("Contents/Resources/site.pyc")
            with open(bsdir + "/Contents/Resources/site.pyc", "wb") as f:
                f.write(imp.get_magic() + struct.pack("<i", 0))
                f.write(marshal.dumps(compile("", "site.py", "exec")))
        if os.path.exists(os.path.join(app_dir,
                                       "Contents/Resources/site.pyo")):
            copy_to_bootstrap_env("Contents/Resources/site.pyo")
            with open(bsdir + "/Contents/Resources/site.pyo", "wb") as f:
                f.write(imp.get_magic() + struct.pack("<i", 0))
        #  Copy the bootstrapping code into the __boot__.py file.
        copy_to_bootstrap_env("Contents/Resources/__boot__.py")
        with open(bsdir + "/Contents/Resources/__boot__.py", "wt") as f:
            f.write(code_source)
        #  Copy the loader program for each script into the bootstrap env.
        copy_to_bootstrap_env("Contents/MacOS/python")
        for exe in dist.get_executables(normalise=False):
            if not exe.include_in_bootstrap_env:
                continue
            exepath = copy_to_bootstrap_env("Contents/MacOS/" + exe.name)
    #  Copy non-python resources (e.g. icons etc) into the bootstrap dir
    copy_to_bootstrap_env("Contents/Info.plist")
    # Include Icon
    if exe.icon is not None:
        copy_to_bootstrap_env("Contents/Resources/" + exe.icon)
    copy_to_bootstrap_env("Contents/PkgInfo")
    with open(os.path.join(app_dir, "Contents", "Info.plist"), "rt") as f:
        infotxt = f.read()
    for nm in os.listdir(os.path.join(app_dir, "Contents", "Resources")):
        if "<string>%s</string>" % (nm, ) in infotxt:
            copy_to_bootstrap_env("Contents/Resources/" + nm)


def zipit(dist, bsdir, zfname):
    """Create the final zipfile of the esky.

    We customize this process for py2app, so that the zipfile contains a
    toplevel "<appname>.app" directory.  This allows users to just extract
    the zipfile and have a proper application all set up and working.
    """

    def get_arcname(fpath):
        return os.path.join(dist.distribution.get_name() + ".app", fpath)

    return create_zipfile(bsdir, zfname, get_arcname, compress=True)


def _make_py2app_cmd(dist_dir, distribution, options, exes):
    exe = exes[0]
    extra_exes = exes[1:]
    cmd = py2app(distribution)
    for (nm, val) in list(options.items()):
        setattr(cmd, nm, val)
    cmd.dist_dir = dist_dir
    cmd.app = [Target(script=exe.script, dest_base=exe.name)]
    cmd.extra_scripts = [e.script for e in extra_exes]
    cmd.finalize_options()
    cmd.plist["CFBundleExecutable"] = exe.name
    old_run = cmd.run

    def new_run():
        #  py2app munges the environment in ways that break things.
        old_deployment_target = os.environ.get("MACOSX_DEPLOYMENT_TARGET",
                                               None)
        old_run()
        if old_deployment_target is None:
            os.environ.pop("MACOSX_DEPLOYMENT_TARGET", None)
        else:
            os.environ["MACOSX_DEPLOYMENT_TARGET"] = old_deployment_target
        #  We need to script file to have the same name as the exe, which
        #  it won't if they have changed it explicitly.
        resdir = os.path.join(dist_dir, distribution.get_name() + ".app",
                              "Contents/Resources")
        scriptf = os.path.join(resdir, exe.name + ".py")
        if not os.path.exists(scriptf):
            old_scriptf = os.path.basename(exe.script)
            old_scriptf = os.path.join(resdir, old_scriptf)
            shutil.move(old_scriptf, scriptf)

    cmd.run = new_run
    return cmd

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

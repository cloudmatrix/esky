#  Copyright (c) 2009, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.bdist_esky:  distutils command to freeze apps in esky format

Importing this module makes "bdist_esky" available as a distutils command.
This command will freeze the given scripts and package them into a zipfile
named with the application name, version and platform.

The resulting zipfile is conveniently in the format expected by the default
SimpleVersionFinder.  It will be named "appname-version.platform.zip"

"""

import os
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

import distutils.command
from distutils.core import Command
from distutils.util import convert_path

import bbfreeze

import esky.bootstrap
from esky.util import get_platform, is_core_dependency


class bdist_esky(Command):
    """Create a frozen application in 'esky' format.

    This distutils command can be used to freeze an application in the
    format expected by esky.  It interprets the following standard 
    distutils options:

       scripts:  list of scripts to freeze as executables;
                 to make a gui-only script, name it 'script.pyw'

       data_files:  copied into the frozen app directory

       package_data:  copied into library.zip alongside the module code

    To further customize the behaviour of the bdist_esky command, you can
    specify the following custom options:

        includes:  a list of modules to explicitly include in the freeze

        excludes:  a list of modules to explicitly exclude from the freeze

        bootstrap_module:  a custom module to use for esky bootstrapping;
                           the default just calls esky.bootstrap.bootstap()

    
    """

    description = "create a frozen app in 'esky' format"

    user_options = [
                    ('dist-dir=', 'd',
                     "directory to put final built distributions in"),
                    ('bootstrap-module=', None,
                     "module to use for bootstrapping esky apps"),
                    ('includes=', None,
                     "list of modules to specifically include"),
                    ('excludes=', None,
                     "list of modules to specifically exclude"),
                   ]

    def initialize_options(self):
        self.dist_dir = None
        self.includes = []
        self.excludes = []
        self.bootstrap_module = None

    def finalize_options(self):
        self.set_undefined_options('bdist',('dist_dir', 'dist_dir'))

    def run(self):
        fullname = self.distribution.get_fullname()
        platform = get_platform()
        bsdir = os.path.join(self.dist_dir,"%s.%s"%(fullname,platform,))
        fdir = os.path.join(bsdir,"%s.%s"%(fullname,platform,))
        if os.path.exists(bsdir):
            shutil.rmtree(bsdir)
        os.makedirs(fdir)
        self.freeze_scripts(fdir)
        self.add_data_files(fdir)
        self.add_package_data(fdir)
        #  Create the bootstrap environment...
        bslib_path = os.path.join(bsdir,"library.zip")
        bslib = zipfile.PyZipFile(bslib_path,"w",zipfile.ZIP_STORED)
        #  ...containing the bootstrapping module
        code_source = inspect.getsource(esky.bootstrap)
        code = imp.get_magic() + struct.pack("<i",0)
        code += marshal.dumps(compile(code_source,"bootstrap.py","exec"))
        bslib.writestr(zipfile.ZipInfo("bootstrap.pyc",(2000,1,1,0,0,0)),code)
        #  ...and the main module which uses it
        if self.bootstrap_module is None:
            code_source = "from bootstrap import bootstrap\nbootstrap()"
        else:
            bsmodule = __import__(self.bootstrap_module)
            code_source = inspect.getsource(bsmodule)
        code = imp.get_magic() + struct.pack("<i",0)
        code += marshal.dumps(compile(code_source,"__main__.py","exec"))
        bslib.writestr(zipfile.ZipInfo("__main__.pyc",(2000,1,1,0,0,0)),code)
        bslib.close()
        manifest = ["library.zip"]
        if self.distribution.has_scripts():
            for s in self.distribution.scripts:
                nm = os.path.basename(s)
                if nm.endswith(".py") or nm.endswith(".pyw"):
                    nm = ".".join(nm.split(".")[:-1])
                if sys.platform == "win32":
                    nm += ".exe"
                self.copy_file(os.path.join(fdir,nm),os.path.join(bsdir,nm))
                manifest.append(nm)
        for nm in os.listdir(fdir):
            if is_core_dependency(nm):
                self.copy_file(os.path.join(fdir,nm),os.path.join(bsdir,nm))
                manifest.append(nm)
        f_manifest = open(os.path.join(fdir,"esky-bootstrap.txt"),"wt")
        for nm in manifest:
            f_manifest.write(nm)
            f_manifest.write("\n")
        f_manifest.close()
        #  Zip up the distribution
        zfname = os.path.join(self.dist_dir,"%s.%s.zip"%(fullname,platform,))
        zf = zipfile.ZipFile(zfname,"w")
        for (dirpath,dirnames,filenames) in os.walk(bsdir):
            for fn in filenames:
                fpath = os.path.join(dirpath,fn)
                zpath = fpath[len(bsdir)+1:]
                zf.write(fpath,zpath)
        zf.close()
        shutil.rmtree(bsdir)

    def freeze_scripts(self,fdir):
        """Do a standard bbfreeze of the given scripts."""
        f = bbfreeze.Freezer(fdir,includes=self.includes,excludes=self.excludes)
        f.linkmethod = "loader"
        f.addModule("esky")
        if self.distribution.has_scripts():
            for s in self.distribution.scripts:
                f.addScript(s,gui_only=s.endswith(".pyw"))
        f()

    def add_data_files(self,fdir):
        """Add any data_files under the frozen directory."""
        if self.distribution.data_files:
            for datafile in self.distribution.data_files:
                #  Plain strings get placed in the root dist directory
                if isinstance(datafile,basestring):
                    datafile = ("",[datafile])
                (df_dest,df_sources) = datafile
                if os.path.isabs(df_dest):
                    raise ValueError("cant freeze absolute data_file paths (%s)" % (df_dest,))
                df_dest = os.path.join(fdir,convert_path(df_dest))
                if not os.path.isdir(df_dest):
                    self.mkpath(df_dest)
                for df_src in df_sources:
                    df_src = convert_path(df_src)
                    self.copy_file(df_src,df_dest)
 
    def add_package_data(self,fdir):
        """Add any package_data to the frozen library.zip"""
        lib = zipfile.ZipFile(os.path.join(fdir,"library.zip"),"a")
        if self.distribution.package_data:
            for pkg,data in self.distribution.package_data.iteritems():
                pkg_dir = self.get_package_dir(pkg)
                pkg_path = pkg.replace(".","/")
                if isinstance(data,basestring):
                    data = [data]
                for dpattern in data:
                    dfiles = glob(os.path.join(pkg_dir,convert_path(dpattern)))
                    for nm in dfiles:
                        arcnm = pkg_path + nm[len(pkg_dir):]
                        lib.write(nm,arcnm)
        lib.close()

    def get_package_dir(self,pkg):
        """Return directory where the given package is location."""
        inpath = pkg.split(".")
        outpath = []
        if not self.distribution.package_dir:
            outpath = inpath
        else:
            while inpath:
                try:
                    dir = self.distribution.package_dir[".".join(inpath)]
                except KeyError:
                    outpath.insert(0, inpath[-1])
                    del inpath[-1]
                else:
                    outpath.insert(0, dir)
                    break
            else:
                try:
                    dir = self.package_dir[""]
                except KeyError:
                    pass
                else:
                    outpath.insert(0, dir)
        if outpath:
            return os.path.join(*outpath)
        else:
            return ""



distutils.command.__all__.append("bdist_esky")
sys.modules["distutils.command.bdist_esky"] = sys.modules["esky.bdist_esky"]


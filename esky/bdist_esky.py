"""

  esky.bdist_esky:  distutils command to freeze apps in esky format

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

import distutils.command
from distutils.core import Command

import bbfreeze
from bbfreeze.freezer import replace_paths_in_code

import esky.bootstrap


# Things to do:
#
#   * bundle package_data into the library.zip
#   * copy data_files into the distribution directory
#



class bdist_esky(Command):

    description = "create a frozen app in 'esky' format"

    user_options = [
                    ('dist-dir=', 'd',
                     "directory to put final built distributions in"),
                   ]

    def initialize_options(self):
        self.dist_dir = None

    def finalize_options(self):
        self.set_undefined_options('bdist',('dist_dir', 'dist_dir'))

    def run(self):
        fdir = os.path.join(self.dist_dir,self.distribution.get_fullname())
        f = bbfreeze.Freezer(fdir)
        f.linkmethod = "loader"
        f.addModule("esky")
        if self.distribution.has_scripts():
            for s in self.distribution.scripts:
                f.addScript(s,gui_only=s.endswith(".pyw"))
        f()
        bscode_source = inspect.getsource(esky.bootstrap)
        bscode = imp.get_magic() + struct.pack("<i",time.time())
        bscode += marshal.dumps(compile(bscode_source,"__main__.py","exec"))
        bslib_path = os.path.join(fdir,"bootstrap-library.zip")
        bslib = zipfile.PyZipFile(bslib_path,"w",zipfile.ZIP_STORED)
        bslib.writestr("__main__.pyc",bscode)
        bslib.close()


distutils.command.__all__.append("bdist_esky")
sys.modules["distutils.command.bdist_esky"] = sys.modules["esky.bdist_esky"]


#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.bdist_esky:  distutils command to freeze apps in esky format

Importing this module makes "bdist_esky" available as a distutils command.
This command will freeze the given scripts and package them into a zipfile
named with the application name, version and platform.

The resulting zipfile is conveniently in the format expected by the class
DefaultVersionFinder.  It will be named "appname-version.platform.zip"

"""

from __future__ import with_statement


import os
import re
import sys
import shutil
import zipfile
import tempfile
import hashlib
import inspect
from glob import glob

import distutils.command
from distutils.core import Command
from distutils.util import convert_path

import esky.patch
from esky.util import get_platform, is_core_dependency, create_zipfile, \
                      split_app_version, join_app_version, ESKY_CONTROL_DIR, \
                      ESKY_APPDATA_DIR, really_rmtree

if sys.platform == "win32":
    from esky import winres
    from xml.dom import minidom

try:
    from esky.bdist_esky import pypyc
except ImportError, e:
    pypyc = None
    PYPYC_ERROR = e
    COMPILED_BOOTSTRAP_CACHE = None
else:
    COMPILED_BOOTSTRAP_CACHE = os.path.dirname(__file__)
    if not os.path.isdir(COMPILED_BOOTSTRAP_CACHE):
        COMPILED_BOOTSTRAP_CACHE = None



#  setuptools likes to be imported before anything else that
#  might monkey-patch distutils.  We don't actually use it,
#  this is just to avoid errors with cx_Freeze.
try:
    import setuptools
except ImportError:
    pass


_FREEZERS = {}
try:
    from esky.bdist_esky import f_py2exe
    _FREEZERS["py2exe"] = f_py2exe
except ImportError:
    _FREEZERS["py2exe"] = None
try:
    from esky.bdist_esky import f_py2app
    _FREEZERS["py2app"] = f_py2app
except ImportError:
    _FREEZERS["py2app"] = None
try:
    from esky.bdist_esky import f_bbfreeze
    _FREEZERS["bbfreeze"] = f_bbfreeze
except ImportError:
    _FREEZERS["bbfreeze"] = None
try:
    from esky.bdist_esky import f_cxfreeze
    _FREEZERS["cxfreeze"] = f_cxfreeze
    _FREEZERS["cx_Freeze"] = f_cxfreeze
    _FREEZERS["cx_freeze"] = f_cxfreeze
except ImportError:
    _FREEZERS["cxfreeze"] = None
    _FREEZERS["cx_Freeze"] = None
    _FREEZERS["cx_freeze"] = None


class Executable(unicode):
    """Class to hold information about a specific executable.

    This class provides a uniform way to specify extra meta-data about
    a frozen executable.  By setting various keyword arguments, you can
    specify e.g. the icon, and whether it is a gui-only script.

    Some freezer modules require all items in the "scripts" argument to
    be strings naming real files.  This is therefore a subclass of unicode,
    and if it refers only to in-memory code then its string value will be
    the path to this very file.  I know it's ugly, but it works.
    """

    def __new__(cls,script,**kwds):
        if isinstance(script,basestring):
            return unicode.__new__(cls,script)
        else:
            return unicode.__new__(cls,__file__)

    def __init__(self,script,name=None,icon=None,gui_only=None,
                      include_in_bootstrap_env=True,**kwds):
        unicode.__init__(self)
        if isinstance(script,Executable):
            script = script.script
            if name is None:
                name = script.name
            if gui_only is None:
                gui_only = script.gui_only
        if not isinstance(script,basestring):
            if name is None:
                raise TypeError("Must specify name if script is not a file")
        self.script = script
        self.include_in_bootstrap_env = include_in_bootstrap_env
        self.icon = icon
        self._name = name
        self._gui_only = gui_only
        self._kwds = kwds

    @property
    def name(self):
        if self._name is not None:
            nm = self._name
        else:
            if not isinstance(self.script,basestring):
                raise TypeError("Must specify name if script is not a file")
            nm = os.path.basename(self.script)
            if nm.endswith(".py"):
                nm = nm[:-3]
            elif nm.endswith(".pyw"):
                nm = nm[:-4]
        if sys.platform == "win32" and not nm.endswith(".exe"):
            nm += ".exe"
        return nm

    @property
    def gui_only(self):
        if self._gui_only is None:
            if not isinstance(self.script,basestring):
                return False
            else:
                return self.script.endswith(".pyw")
        else:
            return self._gui_only



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

        freezer_module:  name of freezer module to use; currently py2exe,
                         py2app,  bbfreeze and cx-freeze are supported.

        freezer_options: dict of options to pass through to the underlying
                         freezer module.

        bootstrap_module:  a custom module to use for esky bootstrapping;
                           the default calls esky.bootstrap.bootstrap()

        bootstrap_code:  a custom code string to use for esky bootstrapping;
                         this precludes the use of the bootstrap_module option.
                         If a non-string object is given, its source is taken
                         using inspect.getsource().

        compile_bootstrap_exes:  whether to compile the bootstrapping code to a
                                 stand-alone exe; this requires PyPy installed
                                 and the bootstrap code to be valid RPython.
                                 When false, the bootstrap env will use a
                                 trimmed-down copy of the freezer module exe.

        dont_run_startup_hooks:  don't force all executables to call
                                 esky.run_startup_hooks() on startup.

        bundle_msvcrt:  whether to bundle the MSVCRT DLLs, manifest files etc
                        as a private assembly.  The default is False; only
                        those with a valid license to redistriute these files
                        should enable it.



        pre_freeze_callback:  function to call just before starting to freeze
                              the application; this is a good opportunity to
                              customize the bdist_esky instance.

        pre_zip_callback:  function to call just before starting to zip up
                           the frozen application; this is a good opportunity
                           to e.g. sign the resulting executables.
    
    """

    description = "create a frozen app in 'esky' format"

    user_options = [
                    ('dist-dir=', 'd',
                     "directory to put final built distributions in"),
                    ('freezer-module=', None,
                     "module to use for freezing the application"),
                    ('freezer-options=', None,
                     "options to pass to the underlying freezer module"),
                    ('bootstrap-module=', None,
                     "module to use for bootstrapping the application"),
                    ('bootstrap-code=', None,
                     "code to use for bootstrapping the application"),
                    ('compile-bootstrap-exes=', None,
                     "whether to compile the bootstrapping exes with pypy"),
                    ('bundle-msvcrt=', None,
                     "whether to bundle MSVCRT as private assembly"),
                    ('includes=', None,
                     "list of modules to specifically include"),
                    ('excludes=', None,
                     "list of modules to specifically exclude"),
                    ('dont-run-startup-hooks=', None,
                     "don't force execution of esky.run_startup_hooks()"),
                    ('pre-freeze-callback=', None,
                     "function to call just before starting to freeze the app"),
                    ('pre-zip-callback=', None,
                     "function to call just before starting to zip up the app"),
                    ('enable-appdata-dir=', None,
                     "enable new 'appdata' directory layout (will go away after the 0.9.X series)"),
                   ]

    boolean_options = ["bundle-msvcrt","dont-run-startup-hooks","compile-bootstrap-exes","enable-appdata-dir"]

    def initialize_options(self):
        self.dist_dir = None
        self.includes = []
        self.excludes = []
        self.freezer_module = None
        self.freezer_options = {}
        self.bundle_msvcrt = False
        self.dont_run_startup_hooks = False
        self.bootstrap_module = None
        self.bootstrap_code = None
        self.compile_bootstrap_exes = False
        self._compiled_exes = {}
        self.pre_freeze_callback = None
        self.pre_zip_callback = None
        self.enable_appdata_dir = False

    def finalize_options(self):
        self.set_undefined_options('bdist',('dist_dir', 'dist_dir'))
        if self.compile_bootstrap_exes and pypyc is None:
            raise PYPYC_ERROR
        if self.freezer_module is None:
            for freezer_module in ("py2exe","py2app","bbfreeze","cxfreeze"):
                self.freezer_module = _FREEZERS[freezer_module]
                if self.freezer_module is not None:
                    break
            else:
                err = "no supported freezer modules found"
                err += " (try installing bbfreeze)"
                raise RuntimeError(err)
        else:
            try:
                freezer = _FREEZERS[self.freezer_module]
            except KeyError:
                err = "freezer module not supported: '%s'"
                err = err % (self.freezer_module,)
                raise RuntimeError(err)
            else:
                if freezer is None:
                    err = "freezer module not found: '%s'"
                    err = err % (self.freezer_module,)
                    raise RuntimeError(err)
            self.freezer_module = freezer
        if isinstance(self.pre_freeze_callback,basestring):
            self.pre_freeze_callback = self._name2func(self.pre_freeze_callback)
        if isinstance(self.pre_zip_callback,basestring):
            self.pre_zip_callback = self._name2func(self.pre_zip_callback)

    def _name2func(self,name):
        """Convert a dotted name into a function reference."""
        if "." not in name:
            return globals()[name]
        modname,funcname = name.rsplit(".",1)
        mod = __import__(modname,fromlist=[funcname])
        return getattr(mod,funcname)

    def run(self):
        self.tempdir = tempfile.mkdtemp()
        try:
            self._run()
        finally:
            really_rmtree(self.tempdir)

    def _run(self):
        self._run_initialise_dirs()
        if self.pre_freeze_callback is not None:
            self.pre_freeze_callback(self)
        self._run_freeze_scripts()
        if self.pre_zip_callback is not None:
            self.pre_zip_callback(self)
        self._run_create_zipfile()

    def _run_initialise_dirs(self):
        """Create the dirs into which to freeze the app."""
        fullname = self.distribution.get_fullname()
        platform = get_platform()
        self.bootstrap_dir = os.path.join(self.dist_dir,
                                          "%s.%s"%(fullname,platform,))
        if self.enable_appdata_dir:
            self.freeze_dir = os.path.join(self.bootstrap_dir,ESKY_APPDATA_DIR,
                                           "%s.%s"%(fullname,platform,))
        else:
            self.freeze_dir = os.path.join(self.bootstrap_dir,
                                           "%s.%s"%(fullname,platform,))
        if os.path.exists(self.bootstrap_dir):
            really_rmtree(self.bootstrap_dir)
        os.makedirs(self.freeze_dir)

    def _run_freeze_scripts(self):
        """Call the selected freezer module to freeze the scripts."""
        fullname = self.distribution.get_fullname()
        platform = get_platform()
        self.freezer_module.freeze(self)
        if platform != "win32":
            lockfile = os.path.join(self.freeze_dir,ESKY_CONTROL_DIR,"lockfile.txt")
            with open(lockfile,"w") as lf:
                lf.write("this file is used by esky to lock the version dir\n")

    def _run_create_zipfile(self):
        """Zip up the final distribution."""
        print "zipping up the esky"
        fullname = self.distribution.get_fullname()
        platform = get_platform()
        zfname = os.path.join(self.dist_dir,"%s.%s.zip"%(fullname,platform,))
        if hasattr(self.freezer_module,"zipit"):
            self.freezer_module.zipit(self,self.bootstrap_dir,zfname)
        else:
            create_zipfile(self.bootstrap_dir,zfname,compress=True)
        really_rmtree(self.bootstrap_dir)

    def _obj2code(self,obj):
        """Convert an object to some python source code.

        Iterables are flattened, None is elided, strings are included verbatim,
        open files are read and anything else is passed to inspect.getsource().
        """
        if obj is None:
            return ""
        if isinstance(obj,basestring):
            return obj
        if hasattr(obj,"read"):
            return obj.read()
        try:
            return "\n\n\n".join(self._obj2code(i) for i in obj)
        except TypeError:
            return inspect.getsource(obj)

    def get_bootstrap_code(self):
        """Get any extra code to be executed by the bootstrapping exe.

        This method interprets the bootstrap-code and bootstrap-module settings
        to construct any extra bootstrapping code that must be executed by
        the frozen bootstrap executable.  It is returned as a string.
        """
        bscode = self.bootstrap_code
        if bscode is None:
            if self.bootstrap_module is not None:
                bscode = __import__(self.bootstrap_module)
                for submod in self.bootstrap_module.split(".")[1:]:
                    bscode = getattr(bscode,submod)
        bscode = self._obj2code(bscode)
        return bscode

    def get_executables(self,normalise=True):
        """Yield a normalised Executable instance for each script to be frozen.

        If "normalise" is True (the default) then the user-provided scripts
        will be rewritten to decode any non-filename items specified as part
        of the script, and to include the esky startup code.  If the freezer
        has a better way of doing these things, it should pass normalise=False.
        """
        if normalise:
            if not os.path.exists(os.path.join(self.tempdir,"scripts")):
                os.mkdir(os.path.join(self.tempdir,"scripts"))
        if self.distribution.has_scripts():
            for s in self.distribution.scripts:
                if isinstance(s,Executable):
                    exe = s
                else:
                    exe = Executable(s)
                if normalise:
                    #  Give the normalised script file a name matching that
                    #  specified, since some freezers only take the filename.
                    name = exe.name
                    if sys.platform == "win32" and name.endswith(".exe"):
                        name = name[:-4]
                    if exe.endswith(".pyw"):
                        ext = ".pyw"
                    else:
                        ext = ".py"
                    script = os.path.join(self.tempdir,"scripts",name+ext)
                    #  Get the code for the target script.
                    #  If it's a single string then interpret it as a filename,
                    #  otherwise feed it into the _obj2code logic.
                    if isinstance(exe.script,basestring):
                        with open(exe.script,"rt") as f:
                            code = f.read()
                    else:
                        code = self._obj2code(exe.script)
                    #  Check that the code actually compiles - sometimes it
                    #  can be hard to get a good message out of the freezer.
                    compile(code,"","exec")
                    #  Augment the given code with special esky-related logic.
                    with open(script,"wt") as fOut:
                        lines = (ln+"\n" for ln in code.split("\n"))
                        #  Keep any leading comments and __future__ imports
                        #  at the start of the file.
                        for ln in lines:
                            if ln.strip():
                                if not ln.strip().startswith("#"):
                                    if "__future__" not in ln:
                                        break
                            fOut.write(ln)
                        #  Run the startup hooks before any actual code.
                        if not self.dont_run_startup_hooks:
                            fOut.write("import esky\n")
                            fOut.write("esky.run_startup_hooks()\n")
                            fOut.write("\n")
                        #  Then just include the rest of the script code.
                        fOut.write(ln)
                        for ln in lines:
                            fOut.write(ln)
                    new_exe = Executable(script)
                    new_exe.__dict__.update(exe.__dict__)
                    new_exe.script = script
                    exe = new_exe
                yield exe

    def get_data_files(self):
        """Yield (source,destination) tuples for data files.

        This method generates the names of all data file to be included in
        the frozen app.  They should be placed directly into the freeze
        directory as raw files.
        """
        fdir = self.freeze_dir
        if sys.platform == "win32" and self.bundle_msvcrt:
            for (src,dst) in self.get_msvcrt_private_assembly_files():
                yield (src,dst)
        if self.distribution.data_files:
            for datafile in self.distribution.data_files:
                #  Plain strings get placed in the root dist directory.
                if isinstance(datafile,basestring):
                    datafile = ("",[datafile])
                (dst,sources) = datafile
                if os.path.isabs(dst):
                    err = "cant freeze absolute data_file paths (%s)"
                    err = err % (dst,)
                    raise ValueError(err)
                dst = convert_path(dst)
                for src in sources:
                    src = convert_path(src)
                    yield (src,os.path.join(dst,os.path.basename(src)))
 
    def get_package_data(self):
        """Yield (source,destination) tuples for package data files.

        This method generates the names of all package data files to be
        included in the frozen app.  They should be placed in the library.zip
        or equivalent, alongside the python files for that package.
        """
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
                        yield (nm,arcnm)

    def get_package_dir(self,pkg):
        """Return directory where the given package is located.

        This was largely swiped from distutils, with some cleanups.
        """
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

    @staticmethod
    def get_msvcrt_private_assembly_files():
        """Get (source,destination) tuples for the MSVCRT DLLs, manifest etc.

        This method generates data_files tuples for the MSVCRT DLLs, manifest
        and associated paraphernalia.  Including these files is required for
        newer Python versions if you want to run on machines that don't have
        the latest C runtime installed *and* you don't want to run the special
        "vcredist_x86.exe" program during your installation process.

        Bundling is only performed on win32 paltforms, and only if you enable
        it explicitly.  Before doing so, carefully check whether you have a
        license to distribute these files.
        """
        cls = bdist_esky
        msvcrt_info = cls._get_msvcrt_info()
        if msvcrt_info is not None:
            msvcrt_name = msvcrt_info[0]
            #  Find installed manifest file with matching info
            for candidate in cls._find_msvcrt_manifest_files(msvcrt_name):
                manifest_file, msvcrt_dir = candidate
                try:
                    with open(manifest_file,"rb") as mf:
                        manifest_data = mf.read()
                        for info in msvcrt_info:
                            if info.encode() not in manifest_data:
                                break
                        else:
                            break
                except EnvironmentError:
                    pass
            else:
                err = "manifest for %s not found" % (msvcrt_info,)
                raise RuntimeError(err)
            #  Copy the manifest and matching directory into the freeze dir.
            manifest_name = msvcrt_name + ".manifest"
            yield (manifest_file,os.path.join(msvcrt_name,manifest_name))
            for fnm in os.listdir(msvcrt_dir):
                yield (os.path.join(msvcrt_dir,fnm),
                       os.path.join(msvcrt_name,fnm))

    @staticmethod
    def _get_msvcrt_info():
        """Get info about the MSVCRT in use by this python executable.

        This parses the name, version and public key token out of the exe
        manifest and returns them as a tuple.
        """
        try:
            manifest_str = winres.get_app_manifest()
        except EnvironmentError:
            return None
        manifest = minidom.parseString(manifest_str)
        for assembly in manifest.getElementsByTagName("assemblyIdentity"):
            name = assembly.attributes["name"].value
            if name.startswith("Microsoft") and name.endswith("CRT"):
                version = assembly.attributes["version"].value 
                pubkey = assembly.attributes["publicKeyToken"].value 
                return (name,version,pubkey)
        return None
        
    
    @staticmethod
    def _find_msvcrt_manifest_files(name):
        """Search the system for candidate MSVCRT manifest files.

        This method yields (manifest_file,msvcrt_dir) tuples giving a candidate
        manifest file for the given assembly name, and the directory in which
        the actual assembly data files are found.
        """
        cls = bdist_esky
        #  Search for redist files in a Visual Studio install
        progfiles = os.path.expandvars("%PROGRAMFILES%")
        for dnm in os.listdir(progfiles):
            if dnm.lower().startswith("microsoft visual studio"):
                dpath = os.path.join(progfiles,dnm,"VC","redist")
                for (subdir,_,filenames) in os.walk(dpath):
                    for fnm in filenames:
                        if name.lower() in fnm.lower():
                            if fnm.lower().endswith(".manifest"):
                                mf = os.path.join(subdir,fnm)
                                md = cls._find_msvcrt_dir_for_manifest(name,mf)
                                if md is not None:
                                    yield (mf,md)
        #  Search for manifests installed in the WinSxS directory
        winsxs_m = os.path.expandvars("%WINDIR%\\WinSxS\\Manifests")
        for fnm in os.listdir(winsxs_m):
            if name.lower() in fnm.lower():
                if fnm.lower().endswith(".manifest"):
                    mf = os.path.join(winsxs_m,fnm)
                    md = cls._find_msvcrt_dir_for_manifest(name,mf)
                    if md is not None:
                        yield (mf,md)
        winsxs = os.path.expandvars("%WINDIR%\\WinSxS")
        for fnm in os.listdir(winsxs):
            if name.lower() in fnm.lower():
                if fnm.lower().endswith(".manifest"):
                    mf = os.path.join(winsxs,fnm)
                    md = cls._find_msvcrt_dir_for_manifest(name,mf)
                    if md is not None:
                        yield (mf,md)

    @staticmethod
    def _find_msvcrt_dir_for_manifest(msvcrt_name,manifest_file):
        """Find the directory containing data files for the given manifest.

        This searches a few common locations for the data files that go with
        the given manifest file.  If a suitable directory is found then it is
        returned, otherwise None is returned.
        """
        #  The manifest file might be next to the dir, inside the dir, or
        #  in a subdir named "Manifests".  Walk around till we find it.
        msvcrt_dir = ".".join(manifest_file.split(".")[:-1])
        if os.path.isdir(msvcrt_dir):
            return msvcrt_dir
        msvcrt_basename = os.path.basename(msvcrt_dir)
        msvcrt_parent = os.path.dirname(os.path.dirname(msvcrt_dir))
        msvcrt_dir = os.path.join(msvcrt_parent,msvcrt_basename)
        if os.path.isdir(msvcrt_dir):
            return msvcrt_dir
        msvcrt_dir = os.path.join(msvcrt_parent,msvcrt_name)
        if os.path.isdir(msvcrt_dir):
            return msvcrt_dir
        return None


    def compile_to_bootstrap_exe(self,exe,source,relpath=None):
        """Compile the given sourcecode into a bootstrapping exe.

        This method compiles the given sourcecode into a stand-alone exe using
        PyPy, then stores that in the bootstrap env under the name of the given
        Executable object.  If the source has been previously compiled then a
        cached version of the exe may be used.
        """
        if not relpath:
            relpath = exe.name
        source = "__rpython__ = True\n" + source
        cdir = os.path.join(self.tempdir,"compile")
        if not os.path.exists(cdir):
            os.mkdir(cdir)
        source_hash = hashlib.md5(source).hexdigest()
        outname = "bootstrap_%s.%s" % (source_hash,get_platform())
        if exe.gui_only:
            outname += ".gui"
        if sys.platform == "win32":
            outname += ".exe"
        #  First try to use a precompiled version.
        if COMPILED_BOOTSTRAP_CACHE is not None:
            outfile = os.path.join(COMPILED_BOOTSTRAP_CACHE,outname)
            if os.path.exists(outfile):
                return self.copy_to_bootstrap_env(outfile,relpath)
        #  Otherwise we have to compile it anew.
        try:
            outfile = self._compiled_exes[(source_hash,exe.gui_only)]
        except KeyError:
            infile = os.path.join(cdir,"bootstrap.py")
            outfile = os.path.join(cdir,outname)
            with open(infile,"wt") as f:
                f.write(source)
            opts = dict(gui_only=exe.gui_only)
            pypyc.compile_rpython(infile,outfile,**opts)
            self._compiled_exes[(source_hash,exe.gui_only)] = outfile
        #  Try to save the compiled exe for future use.
        if COMPILED_BOOTSTRAP_CACHE is not None:
            cachedfile = os.path.join(COMPILED_BOOTSTRAP_CACHE,outname)
            try:
                shutil.copy2(outfile,cachedfile)
            except EnvironmentError:
                pass
        return self.copy_to_bootstrap_env(outfile,relpath)

    def copy_to_bootstrap_env(self,src,dst=None):
        """Copy the named file into the bootstrap environment.

        The filename is also added to the bootstrap manifest.
        """
        if dst is None:
            dst = src
        srcpath = os.path.join(self.freeze_dir,src)
        dstpath = os.path.join(self.bootstrap_dir,dst)
        if os.path.isdir(srcpath):
            self.copy_tree(srcpath,dstpath)
        else:
            if not os.path.isdir(os.path.dirname(dstpath)):
               self.mkpath(os.path.dirname(dstpath))
            self.copy_file(srcpath,dstpath)
        self.add_to_bootstrap_manifest(dstpath)
        return dstpath

    def add_to_bootstrap_manifest(self,dstpath):
        if not os.path.isdir(os.path.join(self.freeze_dir,ESKY_CONTROL_DIR)):
            os.mkdir(os.path.join(self.freeze_dir,ESKY_CONTROL_DIR))
        f_manifest = os.path.join(self.freeze_dir,ESKY_CONTROL_DIR,"bootstrap-manifest.txt")
        with open(f_manifest,"at") as f_manifest:
            f_manifest.seek(0,os.SEEK_END)
            if os.path.isdir(dstpath):
                for (dirnm,_,filenms) in os.walk(dstpath):
                    for fnm in filenms:
                        fpath = os.path.join(dirnm,fnm)
                        dpath = fpath[len(self.bootstrap_dir)+1:]
                        if os.sep != "/":
                            dpath = dpath.replace(os.sep,"/")
                        f_manifest.write(dpath)
                        f_manifest.write("\n")
            else:
                dst = dstpath[len(self.bootstrap_dir)+1:]
                if os.sep != "/":
                    dst = dst.replace(os.sep,"/")
                f_manifest.write(dst)
                f_manifest.write("\n")


class bdist_esky_patch(Command):
    """Create a patch for a frozen application in 'esky' format.

    This distutils command can be used to create a patch file between two
    versions of an application frozen with esky.  Such a patch can be used
    for differential updates between application versions.
    """

    user_options = [
                    ('dist-dir=', 'd',
                     "directory to put final built distributions in"),
                    ('from-version=', None,
                     "version against which to produce patch"),
                   ]

    def initialize_options(self):
        self.dist_dir = None
        self.from_version = None

    def finalize_options(self):
        self.set_undefined_options('bdist',('dist_dir', 'dist_dir'))

    def run(self):
        fullname = self.distribution.get_fullname()
        platform = get_platform()
        vdir = "%s.%s" % (fullname,platform,)
        appname = split_app_version(vdir)[0]
        #  Ensure we have current version's esky, as target for patch.
        target_esky = os.path.join(self.dist_dir,vdir+".zip")
        if not os.path.exists(target_esky):
            self.run_command("bdist_esky")
        #  Generate list of source eskys to patch against.
        if self.from_version:
            source_vdir = join_app_version(appname,self.from_version,platform)
            source_eskys = [os.path.join(self.dist_dir,source_vdir+".zip")]
        else:
            source_eskys = []
            for nm in os.listdir(self.dist_dir):
                if target_esky.endswith(nm):
                    continue
                if nm.startswith(appname+"-") and nm.endswith(platform+".zip"):
                    source_eskys.append(os.path.join(self.dist_dir,nm))
        #  Write each patch, transparently unzipping the esky
        for source_esky in source_eskys:
            target_vdir = os.path.basename(source_esky)[:-4]
            target_version = split_app_version(target_vdir)[1]
            patchfile = vdir+".from-%s.patch" % (target_version,)
            patchfile = os.path.join(self.dist_dir,patchfile)
            print "patching", target_esky, "against", source_esky, "=>", patchfile
            if not self.dry_run:
                try:
                    esky.patch.main(["-Z","diff",source_esky,target_esky,patchfile])
                except:
                    import traceback
                    traceback.print_exc()
                    raise


#  Monkey-patch distutils to include our commands by default.
distutils.command.__all__.append("bdist_esky")
distutils.command.__all__.append("bdist_esky_patch")
sys.modules["distutils.command.bdist_esky"] = sys.modules["esky.bdist_esky"]
sys.modules["distutils.command.bdist_esky_patch"] = sys.modules["esky.bdist_esky"]




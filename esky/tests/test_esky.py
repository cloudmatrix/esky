#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.

from __future__ import with_statement

import sys
import os
import unittest
from os.path import dirname
import subprocess
import shutil
import zipfile
import threading
import tempfile
import urllib2
import hashlib
import tarfile
import time
from contextlib import contextmanager
from SimpleHTTPServer import SimpleHTTPRequestHandler
from BaseHTTPServer import HTTPServer

from distutils.core import setup as dist_setup
from distutils import dir_util

import esky
import esky.patch
import esky.sudo
from esky import bdist_esky
from esky.bdist_esky import Executable
from esky.util import extract_zipfile, deep_extract_zipfile, get_platform, \
                      ESKY_CONTROL_DIR, files_differ, ESKY_APPDATA_DIR, \
                      really_rmtree
from esky.fstransact import FSTransaction

try:
    import py2exe
except ImportError:
    py2exe = None
try:
    import py2app
except ImportError:
    py2app = None
try:
    import bbfreeze
except ImportError:
    bbfreeze = None
try:
    import cx_Freeze
except ImportError:
    cx_Freeze = None
try:
    import pypy
except ImportError:
    pypy = None

sys.path.append(os.path.dirname(__file__))


def assert_freezedir_exists(dist):
    assert os.path.exists(dist.freeze_dir)


if not hasattr(HTTPServer,"shutdown"):
    import socket
    def socketserver_shutdown(self):
        try:
            self.socket.close()
        except socket.error:
            pass
    HTTPServer.shutdown = socketserver_shutdown


@contextmanager
def setenv(key,value):
    oldval = os.environ.get(key,None)
    os.environ[key] = value
    yield
    if oldval is not None:
        os.environ[key] = oldval
    else:
        del os.environ[key]


class TestEsky(unittest.TestCase):

  if py2exe is not None:

    def test_esky_py2exe(self):
        self._run_eskytester({"bdist_esky":{"freezer_module":"py2exe"}})

    def test_esky_py2exe_bundle1(self):
        self._run_eskytester({"bdist_esky":{"freezer_module":"py2exe",
                                            "freezer_options": {
                                              "bundle_files": 1}}})

    def test_esky_py2exe_bundle2(self):
        self._run_eskytester({"bdist_esky":{"freezer_module":"py2exe",
                                            "freezer_options": {
                                              "bundle_files": 2}}})

    def test_esky_py2exe_bundle3(self):
        self._run_eskytester({"bdist_esky":{"freezer_module":"py2exe",
                                            "freezer_options": {
                                              "bundle_files": 3}}})

    def test_esky_py2exe_skiparchive(self):
        self._run_eskytester({"bdist_esky":{"freezer_module":"py2exe",
                                            "freezer_options": {
                                              "skip_archive": True}}})

    def test_esky_py2exe_unbuffered(self):
        self._run_eskytester({"bdist_esky":{"freezer_module":"py2exe",
                                            "freezer_options": {
                                              "unbuffered": True}}})

    def test_esky_py2exe_nocustomchainload(self):
        with setenv("ESKY_NO_CUSTOM_CHAINLOAD","1"):
           bscode = "_chainload = _orig_chainload\nbootstrap()"
           self._run_eskytester({"bdist_esky":{"freezer_module":"py2exe",
                                               "bootstrap_code":bscode}})

    if esky.sudo.can_get_root():
        def test_esky_py2exe_needsroot(self):
            with setenv("ESKY_NEEDSROOT","1"):
               self._run_eskytester({"bdist_esky":{"freezer_module":"py2exe"}})

    if pypy is not None:
        def test_esky_py2exe_pypy(self):
            self._run_eskytester({"bdist_esky":{"freezer_module":"py2exe",
                                                "compile_bootstrap_exes":1}})
        def test_esky_py2exe_unbuffered_pypy(self):
            self._run_eskytester({"bdist_esky":{"freezer_module":"py2exe",
                                                "compile_bootstrap_exes":1,
                                                "freezer_options": {
                                                  "unbuffered": True}}})


  if py2app is not None:

    def test_esky_py2app(self):
        self._run_eskytester({"bdist_esky":{"freezer_module":"py2app"}})

    if esky.sudo.can_get_root():
        def test_esky_py2app_needsroot(self):
            with setenv("ESKY_NEEDSROOT","1"):
                self._run_eskytester({"bdist_esky":{"freezer_module":"py2app"}})

    if pypy is not None:
        def test_esky_py2app_pypy(self):
            self._run_eskytester({"bdist_esky":{"freezer_module":"py2app",
                                                "compile_bootstrap_exes":1}})

  if bbfreeze is not None:

    def test_esky_bbfreeze(self):
        self._run_eskytester({"bdist_esky":{"freezer_module":"bbfreeze"}})

    if sys.platform == "win32":
        def test_esky_bbfreeze_nocustomchainload(self):
            with setenv("ESKY_NO_CUSTOM_CHAINLOAD","1"):
               bscode = "_chainload = _orig_chainload\nbootstrap()"
               self._run_eskytester({"bdist_esky":{"freezer_module":"bbfreeze",
                                                   "bootstrap_code":bscode}})
    if esky.sudo.can_get_root():
        def test_esky_bbfreeze_needsroot(self):
            with setenv("ESKY_NEEDSROOT","1"):
                self._run_eskytester({"bdist_esky":{"freezer_module":"bbfreeze"}})

    if pypy is not None:
        def test_esky_bbfreeze_pypy(self):
            self._run_eskytester({"bdist_esky":{"freezer_module":"bbfreeze",
                                                "compile_bootstrap_exes":1}})

  if cx_Freeze is not None:

    def test_esky_cxfreeze(self):
        self._run_eskytester({"bdist_esky":{"freezer_module":"cxfreeze"}})

    if sys.platform == "win32":
        def test_esky_cxfreeze_nocustomchainload(self):
            with setenv("ESKY_NO_CUSTOM_CHAINLOAD","1"):
               bscode = ["_chainload = _orig_chainload",None]
               self._run_eskytester({"bdist_esky":{"freezer_module":"cxfreeze",
                                                   "bootstrap_code":bscode}})

    if esky.sudo.can_get_root():
        def test_esky_cxfreeze_needsroot(self):
            with setenv("ESKY_NEEDSROOT","1"):
                self._run_eskytester({"bdist_esky":{"freezer_module":"cxfreeze"}})

    if pypy is not None:
        def test_esky_cxfreeze_pypy(self):
            with setenv("ESKY_NO_CUSTOM_CHAINLOAD","1"):
              self._run_eskytester({"bdist_esky":{"freezer_module":"cxfreeze",
                                                 "compile_bootstrap_exes":1}})
 

  def _run_eskytester(self,options):
    """Build and run the eskytester app using the given distutils options.

    The "eskytester" application can be found next to this file, and the
    sequence of tests performed range across "script1.py" to "script3.py".
    """
    olddir = os.path.abspath(os.curdir)
#    tdir = os.path.join(os.path.dirname(__file__),"DIST")
#    if os.path.exists(tdir):
#        really_rmtree(tdir)
#    os.mkdir(tdir)
    tdir = tempfile.mkdtemp()
    server = None
    script2 = None
    try:
        options.setdefault("build",{})["build_base"] = os.path.join(tdir,"build")
        options.setdefault("bdist",{})["dist_dir"] = os.path.join(tdir,"dist")
        #  Set some callbacks to test that they work correctly
        options.setdefault("bdist_esky",{}).setdefault("pre_freeze_callback","esky.tests.test_esky.assert_freezedir_exists")
        options.setdefault("bdist_esky",{}).setdefault("pre_zip_callback",assert_freezedir_exists)
        platform = get_platform()
        deploydir = "deploy.%s" % (platform,)
        esky_root = dirname(dirname(dirname(__file__)))
        os.chdir(tdir)
        shutil.copytree(os.path.join(esky_root,"esky","tests","eskytester"),"eskytester")
        dir_util._path_created.clear()
        #  Build three increasing versions of the test package.
        #  Version 0.2 will include a bundled MSVCRT on win32.
        #  Version 0.3 will be distributed as a patch.
        metadata = dict(name="eskytester",packages=["eskytester"],author="rfk",
                        description="the esky test package",
                        data_files=[("data",["eskytester/datafile.txt"])],
                        package_data={"eskytester":["pkgdata.txt"]},)
        options2 = options.copy()
        options2["bdist_esky"] = options["bdist_esky"].copy()
        options2["bdist_esky"]["bundle_msvcrt"] = True
        script1 = "eskytester/script1.py"
        script2 = Executable([None,open("eskytester/script2.py")],name="script2")
        script3 = "eskytester/script3.py"
        dist_setup(version="0.1",scripts=[script1],options=options,script_args=["bdist_esky"],**metadata)
        dist_setup(version="0.2",scripts=[script1,script2],options=options2,script_args=["bdist_esky"],**metadata)
        dist_setup(version="0.3",scripts=[script2,script3],options=options,script_args=["bdist_esky_patch"],**metadata)
        os.unlink(os.path.join(tdir,"dist","eskytester-0.3.%s.zip"%(platform,)))
        #  Check that the patches apply cleanly
        uzdir = os.path.join(tdir,"unzip")
        deep_extract_zipfile(os.path.join(tdir,"dist","eskytester-0.1.%s.zip"%(platform,)),uzdir)
        with open(os.path.join(tdir,"dist","eskytester-0.3.%s.from-0.1.patch"%(platform,)),"rb") as f:
            esky.patch.apply_patch(uzdir,f)
        shutil.rmtree(uzdir)
        deep_extract_zipfile(os.path.join(tdir,"dist","eskytester-0.2.%s.zip"%(platform,)),uzdir)
        with open(os.path.join(tdir,"dist","eskytester-0.3.%s.from-0.2.patch"%(platform,)),"rb") as f:
            esky.patch.apply_patch(uzdir,f)
        shutil.rmtree(uzdir)
        #  Serve the updates at http://localhost:8000/dist/
        print "running local update server"
        server = HTTPServer(("localhost",8000),SimpleHTTPRequestHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        #  Set up the deployed esky environment for the initial version
        zfname = os.path.join(tdir,"dist","eskytester-0.1.%s.zip"%(platform,))
        os.mkdir(deploydir)
        extract_zipfile(zfname,deploydir)
        #  Run the scripts in order.
        if options["bdist_esky"]["freezer_module"] == "py2app":
            appdir = os.path.join(deploydir,os.listdir(deploydir)[0])
            cmd1 = os.path.join(appdir,"Contents","MacOS","script1")
            cmd2 = os.path.join(appdir,"Contents","MacOS","script2")
            cmd3 = os.path.join(appdir,"Contents","MacOS","script3")
        else:
            appdir = deploydir
            if sys.platform == "win32":
                cmd1 = os.path.join(deploydir,"script1.exe")
                cmd2 = os.path.join(deploydir,"script2.exe")
                cmd3 = os.path.join(deploydir,"script3.exe")
            else:
                cmd1 = os.path.join(deploydir,"script1")
                cmd2 = os.path.join(deploydir,"script2")
                cmd3 = os.path.join(deploydir,"script3")
        print "spawning eskytester script1", options["bdist_esky"]["freezer_module"]
        os.unlink(os.path.join(tdir,"dist","eskytester-0.1.%s.zip"%(platform,)))
        p = subprocess.Popen(cmd1)
        assert p.wait() == 0
        os.unlink(os.path.join(appdir,"tests-completed"))
        print "spawning eskytester script2"
        os.unlink(os.path.join(tdir,"dist","eskytester-0.2.%s.zip"%(platform,)))
        p = subprocess.Popen(cmd2)
        assert p.wait() == 0
        os.unlink(os.path.join(appdir,"tests-completed"))
        print "spawning eskytester script3"
        p = subprocess.Popen(cmd3)
        assert p.wait() == 0
        os.unlink(os.path.join(appdir,"tests-completed"))
    finally:
        if script2:
            script2.script[1].close()
        os.chdir(olddir)
        if sys.platform == "win32":
           # wait for the cleanup-at-exit pocess to finish
           time.sleep(4)
        really_rmtree(tdir)
        if server:
            server.shutdown()
 
  def test_esky_locking(self):
    """Test that locking an Esky works correctly."""
    platform = get_platform()
    appdir = tempfile.mkdtemp()
    try: 
        vdir = os.path.join(appdir,ESKY_APPDATA_DIR,"testapp-0.1.%s" % (platform,))
        os.makedirs(vdir)
        os.mkdir(os.path.join(vdir,ESKY_CONTROL_DIR))
        open(os.path.join(vdir,ESKY_CONTROL_DIR,"bootstrap-manifest.txt"),"wb").close()
        e1 = esky.Esky(appdir,"http://example.com/downloads/")
        assert e1.name == "testapp"
        assert e1.version == "0.1"
        assert e1.platform == platform
        e2 = esky.Esky(appdir,"http://example.com/downloads/")
        assert e2.name == "testapp"
        assert e2.version == "0.1"
        assert e2.platform == platform
        locked = []; errors = [];
        trigger1 = threading.Event(); trigger2 = threading.Event()
        def runit(e,t1,t2):
            def runme():
                try:
                    e.lock()
                except Exception, err:
                    errors.append(err)
                else:
                    locked.append(e)
                t1.set()
                t2.wait()
            return runme
        t1 = threading.Thread(target=runit(e1,trigger1,trigger2))
        t2 = threading.Thread(target=runit(e2,trigger2,trigger1))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert len(locked) == 1
        assert (e1 in locked or e2 in locked)
        assert len(errors) == 1
        assert isinstance(errors[0],esky.EskyLockedError)
    finally:
        shutil.rmtree(appdir)

 
  def test_esky_lock_breaking(self):
    """Test that breaking the lock on an Esky works correctly."""
    appdir = tempfile.mkdtemp()
    try: 
        os.makedirs(os.path.join(appdir,ESKY_APPDATA_DIR,"testapp-0.1",ESKY_CONTROL_DIR))
        open(os.path.join(appdir,ESKY_APPDATA_DIR,"testapp-0.1",ESKY_CONTROL_DIR,"bootstrap-manifest.txt"),"wb").close()
        e1 = esky.Esky(appdir,"http://example.com/downloads/")
        e2 = esky.Esky(appdir,"http://example.com/downloads/")
        trigger1 = threading.Event(); trigger2 = threading.Event()
        errors = []
        def run1():
            try:
                e1.lock()
            except Exception, err:
                errors.append(err)
            trigger1.set()
            trigger2.wait()
        def run2():
            trigger1.wait()
            try:
                e2.lock()
            except esky.EskyLockedError:
                pass
            except Exception, err:
                errors.append(err)
            else:
                errors.append("locked when I shouldn't have")
            e2.lock_timeout = 0.1
            time.sleep(0.5)
            try:
                e2.lock()
            except Exception, err:
                errors.append(err)
            trigger2.set()
        t1 = threading.Thread(target=run1)
        t2 = threading.Thread(target=run2)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert len(errors) == 0, str(errors)
    finally:
        shutil.rmtree(appdir)


  def test_README(self):
    """Ensure that the README is in sync with the docstring.

    This test should always pass; if the README is out of sync it just updates
    it with the contents of esky.__doc__.
    """
    dirname = os.path.dirname
    readme = os.path.join(dirname(dirname(dirname(__file__))),"README.rst")
    if not os.path.isfile(readme):
        f = open(readme,"wb")
        f.write(esky.__doc__.encode())
        f.close()
    else:
        f = open(readme,"rb")
        if f.read() != esky.__doc__:
            f.close()
            f = open(readme,"wb")
            f.write(esky.__doc__.encode())
            f.close()


class TestFSTransact(unittest.TestCase):
    """Testcases for FSTransact."""

    def setUp(self):
        self.testdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.testdir)

    def path(self,path):
        return os.path.join(self.testdir,path)

    def setContents(self,path,contents=""):
        if not os.path.isdir(os.path.dirname(self.path(path))):
            os.makedirs(os.path.dirname(self.path(path)))
        with open(self.path(path),"wb") as f:
            f.write(contents.encode())

    def assertContents(self,path,contents):
        with open(self.path(path),"rb") as f:
            self.assertEquals(f.read().decode(),contents)

    def test_no_move_outside_root(self):
        self.setContents("file1","hello world")
        trn = FSTransaction(self.testdir)
        trn.move(self.path("file1"),"file2")
        trn.commit()
        self.assertContents("file2","hello world")
        trn = FSTransaction(self.testdir)
        self.assertRaises(ValueError,trn.move,self.path("file2"),"../file1")
        trn.abort()

    def test_move_file(self):
        self.setContents("file1","hello world")
        trn = FSTransaction()
        trn.move(self.path("file1"),self.path("file2"))
        self.assertContents("file1","hello world")
        self.assertFalse(os.path.exists(self.path("file2")))
        trn.commit()
        self.assertContents("file2","hello world")
        self.assertFalse(os.path.exists(self.path("file1")))

    def test_copy_file(self):
        self.setContents("file1","hello world")
        trn = FSTransaction()
        trn.copy(self.path("file1"),self.path("file2"))
        self.assertContents("file1","hello world")
        self.assertFalse(os.path.exists(self.path("file2")))
        trn.commit()
        self.assertContents("file1","hello world")
        self.assertContents("file2","hello world")

    def test_move_dir(self):
        self.setContents("dir1/file1","hello world")
        self.setContents("dir1/file2","how are you?")
        self.setContents("dir1/subdir/file3","fine thanks")
        trn = FSTransaction()
        trn.move(self.path("dir1"),self.path("dir2"))
        self.assertContents("dir1/file1","hello world")
        self.assertFalse(os.path.exists(self.path("dir2")))
        trn.commit()
        self.assertContents("dir2/file1","hello world")
        self.assertContents("dir2/file2","how are you?")
        self.assertContents("dir2/subdir/file3","fine thanks")
        self.assertFalse(os.path.exists(self.path("dir1")))

    def test_copy_dir(self):
        self.setContents("dir1/file1","hello world")
        self.setContents("dir1/file2","how are you?")
        self.setContents("dir1/subdir/file3","fine thanks")
        trn = FSTransaction()
        trn.copy(self.path("dir1"),self.path("dir2"))
        self.assertContents("dir1/file1","hello world")
        self.assertFalse(os.path.exists(self.path("dir2")))
        trn.commit()
        self.assertContents("dir2/file1","hello world")
        self.assertContents("dir2/file2","how are you?")
        self.assertContents("dir2/subdir/file3","fine thanks")
        self.assertContents("dir1/file1","hello world")
        self.assertContents("dir1/file2","how are you?")
        self.assertContents("dir1/subdir/file3","fine thanks")

    def test_remove(self):
        self.setContents("dir1/file1","hello there world")
        trn = FSTransaction()
        trn.remove(self.path("dir1/file1"))
        self.assertTrue(os.path.exists(self.path("dir1/file1")))
        trn.commit()
        self.assertFalse(os.path.exists(self.path("dir1/file1")))
        self.assertTrue(os.path.exists(self.path("dir1")))
        trn = FSTransaction()
        trn.remove(self.path("dir1"))
        trn.commit()
        self.assertFalse(os.path.exists(self.path("dir1")))

    def test_remove_abort(self):
        self.setContents("dir1/file1","hello there world")
        trn = FSTransaction()
        trn.remove(self.path("dir1/file1"))
        self.assertTrue(os.path.exists(self.path("dir1/file1")))
        trn.abort()
        self.assertTrue(os.path.exists(self.path("dir1/file1")))
        trn = FSTransaction()
        trn.remove(self.path("dir1"))
        trn.abort()
        self.assertTrue(os.path.exists(self.path("dir1/file1")))
        trn = FSTransaction()
        trn.remove(self.path("dir1"))
        trn.commit()
        self.assertFalse(os.path.exists(self.path("dir1")))

    def test_move_dir_exists(self):
        self.setContents("dir1/file0","zero zero zero")
        self.setContents("dir1/file1","hello world")
        self.setContents("dir1/file2","how are you?")
        self.setContents("dir1/subdir/file3","fine thanks")
        self.setContents("dir2/file1","different contents")
        self.setContents("dir2/file3","a different file")
        self.setContents("dir1/subdir/file3","fine thanks")
        trn = FSTransaction()
        trn.move(self.path("dir1"),self.path("dir2"))
        self.assertContents("dir1/file1","hello world")
        trn.commit()
        self.assertContents("dir2/file0","zero zero zero")
        self.assertContents("dir2/file1","hello world")
        self.assertContents("dir2/file2","how are you?")
        self.assertFalse(os.path.exists(self.path("dir2/file3")))
        self.assertContents("dir2/subdir/file3","fine thanks")
        self.assertFalse(os.path.exists(self.path("dir1")))

    def test_copy_dir_exists(self):
        self.setContents("dir1/file0","zero zero zero")
        self.setContents("dir1/file1","hello world")
        self.setContents("dir1/file2","how are you?")
        self.setContents("dir1/subdir/file3","fine thanks")
        self.setContents("dir2/file1","different contents")
        self.setContents("dir2/file3","a different file")
        self.setContents("dir1/subdir/file3","fine thanks")
        trn = FSTransaction()
        trn.copy(self.path("dir1"),self.path("dir2"))
        self.assertContents("dir1/file1","hello world")
        trn.commit()
        self.assertContents("dir2/file0","zero zero zero")
        self.assertContents("dir2/file1","hello world")
        self.assertContents("dir2/file2","how are you?")
        self.assertFalse(os.path.exists(self.path("dir2/file3")))
        self.assertContents("dir2/subdir/file3","fine thanks")
        self.assertContents("dir1/file0","zero zero zero")
        self.assertContents("dir1/file1","hello world")
        self.assertContents("dir1/file2","how are you?")
        self.assertContents("dir1/subdir/file3","fine thanks")

    def test_move_dir_over_file(self):
        self.setContents("dir1/file0","zero zero zero")
        self.setContents("dir2","actually a file")
        trn = FSTransaction()
        trn.move(self.path("dir1"),self.path("dir2"))
        self.assertContents("dir1/file0","zero zero zero")
        trn.commit()
        self.assertContents("dir2/file0","zero zero zero")
        self.assertFalse(os.path.exists(self.path("dir1")))

    def test_copy_dir_over_file(self):
        self.setContents("dir1/file0","zero zero zero")
        self.setContents("dir2","actually a file")
        trn = FSTransaction()
        trn.copy(self.path("dir1"),self.path("dir2"))
        self.assertContents("dir1/file0","zero zero zero")
        trn.commit()
        self.assertContents("dir2/file0","zero zero zero")
        self.assertContents("dir1/file0","zero zero zero")

    def test_move_file_over_dir(self):
        self.setContents("file0","zero zero zero")
        self.setContents("dir2/myfile","hahahahaha!")
        trn = FSTransaction()
        trn.move(self.path("file0"),self.path("dir2"))
        self.assertContents("file0","zero zero zero")
        self.assertContents("dir2/myfile","hahahahaha!")
        trn.commit()
        self.assertContents("dir2","zero zero zero")
        self.assertFalse(os.path.exists(self.path("file0")))

    def test_copy_file_over_dir(self):
        self.setContents("file0","zero zero zero")
        self.setContents("dir2/myfile","hahahahaha!")
        trn = FSTransaction()
        trn.copy(self.path("file0"),self.path("dir2"))
        self.assertContents("file0","zero zero zero")
        self.assertContents("dir2/myfile","hahahahaha!")
        trn.commit()
        self.assertContents("dir2","zero zero zero")
        self.assertContents("file0","zero zero zero")


class TestPatch(unittest.TestCase):
    """Testcases for esky.patch."""
 
    _TEST_FILES = (
        ("pyenchant-1.2.0.tar.gz","2fefef0868b110b1da7de89c08344dd2"),
        ("pyenchant-1.5.2.tar.gz","fa1e4f3f3c473edd98c7bb0e46eea352"),
        ("pyenchant-1.6.0.tar.gz","3fd7336989764d8d379a367236518439"),
    )

    _TEST_FILES_URL = "http://pypi.python.org/packages/source/p/pyenchant/"

    def setUp(self):
        self.tests_root = dirname(__file__)
        platform = get_platform()
        self.tfdir = tfdir = os.path.join(self.tests_root,"patch-test-files")
        self.workdir = workdir = os.path.join(self.tests_root,"patch-test-temp."+platform)
        if not os.path.isdir(tfdir):
            os.makedirs(tfdir)
        if not os.path.isdir(workdir):
            os.makedirs(workdir)
        #  Ensure we have the expected test files.
        #  Download from PyPI if necessary.
        for (tfname,hash) in self._TEST_FILES:
            tfpath = os.path.join(tfdir,tfname)
            if not os.path.exists(tfpath):
                data = urllib2.urlopen(self._TEST_FILES_URL+tfname).read()
                assert hashlib.md5(data).hexdigest() == hash
                with open(tfpath,"wb") as f:
                    f.write(data)

    def tearDown(self):
        shutil.rmtree(self.workdir)

    def test_patch_bigfile(self):
        tdir = tempfile.mkdtemp()
        try:
            data = [os.urandom(100)*10 for i in xrange(6)]
            for nm in ("source","target"):
                with open(os.path.join(tdir,nm),"wb") as f:
                    for i in xrange(1000):
                        for chunk in data:
                            f.write(chunk)
                data[2],data[3] = data[3],data[2]
            with open(os.path.join(tdir,"patch"),"wb") as f:
                esky.patch.write_patch(os.path.join(tdir,"source"),os.path.join(tdir,"target"),f)
            dgst1 = esky.patch.calculate_digest(os.path.join(tdir,"target"))
            dgst2 = esky.patch.calculate_digest(os.path.join(tdir,"source"))
            self.assertNotEquals(dgst1,dgst2)
            with open(os.path.join(tdir,"patch"),"rb") as f:
                esky.patch.apply_patch(os.path.join(tdir,"source"),f)
            dgst3 = esky.patch.calculate_digest(os.path.join(tdir,"source"))
            self.assertEquals(dgst1,dgst3)
        finally:
            shutil.rmtree(tdir)

    def test_diffing_back_and_forth(self):
        for (tf1,_) in self._TEST_FILES:
            for (tf2,_) in self._TEST_FILES:
                path1 = self._extract(tf1,"source")
                path2 = self._extract(tf2,"target")
                with open(os.path.join(self.workdir,"patch"),"wb") as f:
                    esky.patch.write_patch(path1,path2,f)
                if tf1 != tf2:
                    self.assertNotEquals(esky.patch.calculate_digest(path1),
                                         esky.patch.calculate_digest(path2))
                with open(os.path.join(self.workdir,"patch"),"rb") as f:
                    esky.patch.apply_patch(path1,f)
                self.assertEquals(esky.patch.calculate_digest(path1),
                                  esky.patch.calculate_digest(path2))

    def test_apply_patch(self):
        path1 = self._extract("pyenchant-1.2.0.tar.gz","source")
        path2 = self._extract("pyenchant-1.6.0.tar.gz","target")
        path1 = os.path.join(path1,"pyenchant-1.2.0")
        path2 = os.path.join(path2,"pyenchant-1.6.0")
        pf = os.path.join(self.tfdir,"v1.2.0_to_v1.6.0.patch")
        if not os.path.exists(pf):
            pf = os.path.join(dirname(esky.__file__),"tests","patch-test-files","v1.2.0_to_v1.6.0.patch")
        with open(pf,"rb") as f:
            esky.patch.apply_patch(path1,f)
        self.assertEquals(esky.patch.calculate_digest(path1),
                         esky.patch.calculate_digest(path2))
        

    def _extract(self,filename,dest):
        dest = os.path.join(self.workdir,dest)
        if os.path.exists(dest):
            really_rmtree(dest)
        f = tarfile.open(os.path.join(self.tfdir,filename),"r:gz")
        try:
            f.extractall(dest)
        finally:
            f.close()
        return dest


class TestPatch_cxbsdiff(TestPatch):
    """Test the patching code with cx-bsdiff rather than bsdiff4."""

    def setUp(self):
        self.__orig_bsdiff4 = esky.patch.bsdiff4
        if esky.patch.bsdiff4_cx is not None:
            esky.patch.bsdiff4 = esky.patch.bsdiff4_cx
        return super(TestPatch_cxbsdiff,self).setUp()

    def tearDown(self):
        esky.patch.bsdiff4 = self.__orig_bsdiff4
        return super(TestPatch_cxbsdiff,self).setUp()


class TestPatch_pybsdiff(TestPatch):
    """Test the patching code with pure-python bsdiff4."""

    def setUp(self):
        self.__orig_bsdiff4 = esky.patch.bsdiff4
        esky.patch.bsdiff4 = esky.patch.bsdiff4_py
        return super(TestPatch_pybsdiff,self).setUp()

    def tearDown(self):
        esky.patch.bsdiff4 = self.__orig_bsdiff4
        return super(TestPatch_pybsdiff,self).setUp()
    
        

class TestFilesDiffer(unittest.TestCase):

    def setUp(self):
        self.tdir = tempfile.mkdtemp()

    def _path(self,*names):
        return os.path.join(self.tdir,*names)

    def _differs(self,data1,data2,start=0,stop=None):
        with open(self._path("file1"),"wb") as f:
            f.write(data1.encode("ascii"))
        with open(self._path("file2"),"wb") as f:
            f.write(data2.encode("ascii"))
        return files_differ(self._path("file1"),self._path("file2"),start,stop)

    def test_files_differ(self):
        assert self._differs("one","two")
        assert self._differs("onethreetwo","twothreeone")
        assert self._differs("onethreetwo","twothreeone",3)
        assert not self._differs("onethreetwo","twothreeone",3,-3)
        assert self._differs("onethreetwo","twothreeone",2,-3)
        assert self._differs("onethreetwo","twothreeone",3,-2)

    def tearDown(self):
        shutil.rmtree(self.tdir)


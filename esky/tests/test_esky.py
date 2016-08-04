#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.

from __future__ import print_function
from future import standard_library
standard_library.install_aliases()
from builtins import str, range

import sys
import os
import unittest
from os.path import dirname
import subprocess
import shutil
import threading
import tempfile
import urllib.request, urllib.error, urllib.parse
import hashlib
import tarfile
import time
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler
from http.server import HTTPServer

from distutils.core import setup as dist_setup
from distutils import dir_util

import esky
import esky.patch
from esky.bdist_esky import Executable
import esky.bdist_esky
from esky.util import extract_zipfile, deep_extract_zipfile, get_platform
from esky.util import ESKY_CONTROL_DIR, files_differ, ESKY_APPDATA_DIR
from esky.util import really_rmtree, LOCAL_HTTP_PORT, silence
from esky.fstransact import FSTransaction
import pytest

try:
    import py2exe
except ImportError:
    py2exe = None
try:
    import py2app
except ImportError:
    py2app = None
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


if not hasattr(HTTPServer, "shutdown"):
    import socket

    def socketserver_shutdown(self):
        try:
            self.socket.close()
        except socket.error:
            pass

    HTTPServer.shutdown = socketserver_shutdown


@contextmanager
def setenv(key, value):
    oldval = os.environ.get(key, None)
    os.environ[key] = value
    yield
    if oldval is not None:
        os.environ[key] = oldval
    else:
        del os.environ[key]


class TestEsky(unittest.TestCase):

    if py2exe is not None:

        @pytest.mark.py2exe
        def test_esky_py2exe_bundle1(self):
            self._run_eskytester({"bdist_esky": {"freezer_module": "py2exe",
                                                 "freezer_options": {
                                                     "bundle_files": 1,
                                                 }}})

        @pytest.mark.py2exe
        def test_esky_py2exe_bundle2(self):
            self._run_eskytester({"bdist_esky": {"freezer_module": "py2exe",
                                                 "freezer_options": {
                                                     "bundle_files": 2,
                                                 }}})

        @pytest.mark.py2exe
        def test_esky_py2exe_bundle3(self):
            self._run_eskytester({"bdist_esky": {"freezer_module": "py2exe",
                                                 "freezer_options": {
                                                     "bundle_files": 3,
                                                 }}})

        @pytest.mark.py2exe
        def test_esky_py2exe_skiparchive(self):
            self._run_eskytester({"bdist_esky": {"freezer_module": "py2exe",
                                                 "freezer_options": {
                                                     "skip_archive": True,
                                                 }}})

        @pytest.mark.py2exe
        def test_esky_py2exe_unbuffered(self):
            self._run_eskytester({"bdist_esky": {"freezer_module": "py2exe",
                                                 "freezer_options": {
                                                     "unbuffered": True,
                                                 }}})

        @pytest.mark.py2exe
        def test_esky_py2exe_nocustomchainload(self):
            with setenv("ESKY_NO_CUSTOM_CHAINLOAD", "1"):
                bscode = "_chainload = _orig_chainload\nbootstrap()"
                self._run_eskytester({"bdist_esky":
                                      {"freezer_module": "py2exe",
                                       "bootstrap_code": bscode}})

        if esky.sudo.can_get_root():

            @pytest.mark.py2exe
            def test_esky_py2exe_needsroot(self):
                with setenv("ESKY_NEEDSROOT", "1"):
                    self._run_eskytester({"bdist_esky": {"freezer_module":
                                                         "py2exe"}})

        if pypy is not None:

            @pytest.mark.py2exe
            def test_esky_py2exe_pypy(self):
                self._run_eskytester({"bdist_esky":
                                      {"freezer_module": "py2exe",
                                       "compile_bootstrap_exes": 1}})

            @pytest.mark.py2exe
            def test_esky_py2exe_unbuffered_pypy(self):
                self._run_eskytester({"bdist_esky":
                                      {"freezer_module": "py2exe",
                                       "compile_bootstrap_exes": 1,
                                       "freezer_options": {
                                           "unbuffered": True,
                                       }}})

    if py2app is not None:

        @pytest.mark.py2app
        def test_esky_py2app(self):
            self._run_eskytester({"bdist_esky": {"freezer_module": "py2app"}})

        if esky.sudo.can_get_root():

            @pytest.mark.py2app
            def test_esky_py2app_needsroot(self):
                with setenv("ESKY_NEEDSROOT", "1"):
                    self._run_eskytester({"bdist_esky": {"freezer_module":
                                                         "py2app"}})

        if pypy is not None:

            @pytest.mark.py2app
            def test_esky_py2app_pypy(self):
                self._run_eskytester({"bdist_esky":
                                      {"freezer_module": "py2app",
                                       "compile_bootstrap_exes": 1}})


    if cx_Freeze is not None:

        @pytest.mark.cxfreeze
        def test_esky_cxfreeze(self):
            self._run_eskytester({"bdist_esky": {"freezer_module": "cxfreeze"}})

        if sys.platform == "win32":

            @pytest.mark.cxfreeze
            def test_esky_cxfreeze_nocustomchainload(self):
                with setenv("ESKY_NO_CUSTOM_CHAINLOAD", "1"):
                    bscode = ["_chainload = _orig_chainload", None]
                    self._run_eskytester({"bdist_esky":
                                          {"freezer_module": "cxfreeze",
                                           "bootstrap_code": bscode}})

        if esky.sudo.can_get_root():

            @pytest.mark.cxfreeze
            def test_esky_cxfreeze_needsroot(self):
                with setenv("ESKY_NEEDSROOT", "1"):
                    self._run_eskytester({"bdist_esky": {"freezer_module":
                                                         "cxfreeze"}})

        if pypy is not None:

            @pytest.mark.cxfreeze
            def test_esky_cxfreeze_pypy(self):
                with setenv("ESKY_NO_CUSTOM_CHAINLOAD", "1"):
                    self._run_eskytester({"bdist_esky":
                                          {"freezer_module": "cxfreeze",
                                           "compile_bootstrap_exes": 1}})

    def _run_eskytester(self, options):
        """Build and run the eskytester app using the given distutils options.

        The "eskytester" application can be found next to this file, and the
        sequence of tests performed range across "script1.py" to "script3.py".
        """
        olddir = os.path.abspath(os.curdir)
        tdir = tempfile.mkdtemp()
        server = None
        script2 = None
        try:
            options.setdefault("build", {})[ "build_base"] = os.path.join(tdir, "build")
            options.setdefault("bdist", {})[ "dist_dir"] = os.path.join(tdir, "dist")
            #  Set some callbacks to test that they work correctly
            options.setdefault("bdist_esky", {}).setdefault( "pre_freeze_callback", "esky.tests.test_esky.assert_freezedir_exists")
            options.setdefault("bdist_esky", {}).setdefault( "pre_zip_callback", assert_freezedir_exists)
            options["bdist_esky"].setdefault("excludes", []).extend(["Tkinter", "tkinter"])
            options["bdist_esky"]["compress"] = "ZIP"
            options["bdist_esky"].setdefault("freezer_options", {})['optimize'] = 0
            platform = get_platform()
            deploydir = "deploy.%s" % (platform, )
            esky_root = dirname(dirname(dirname(__file__)))
            os.chdir(tdir)
            shutil.copytree(
                os.path.join(esky_root, "esky", "tests",
                             "eskytester"), "eskytester")
            dir_util._path_created.clear()

            #  Build three increasing versions of the test package.
            #  Version 0.2 will include a bundled MSVCRT on win32.
            #  Version 0.3 will be distributed as a patch.
            metadata = dict(name="eskytester",
                            packages=["eskytester"],
                            author="rfk",
                            description="the esky test package",
                            data_files=[("data", ["eskytester/datafile.txt"])],
                            package_data={"eskytester": ["pkgdata.txt"]})
            options2 = options.copy()
            options2["bdist_esky"] = options["bdist_esky"].copy()
            options2["bdist_esky"]["bundle_msvcrt"] = True
            script1 = "eskytester/script1.py"
            script2 = Executable([None, open("eskytester/script2.py")], name="script2")
            script3 = "eskytester/script3.py"

            with silence():
                dist_setup(version="0.1", scripts=[script1], options=options, script_args=[ "bdist_esky" ], **metadata)
                dist_setup(version="0.2", scripts=[ script1, script2 ], options=options2, script_args=["bdist_esky"], **metadata)
                dist_setup(version="0.3", scripts=[script2, script3], options=options, script_args=[ "bdist_esky_patch" ], **metadata)
                os.unlink(os.path.join(tdir, "dist", "eskytester-0.3.%s.zip" % ( platform, )))

            #  Check that the patches apply cleanly
            uzdir = os.path.join(tdir, "unzip")
            deep_extract_zipfile( os.path.join(tdir, "dist", "eskytester-0.1.%s.zip" % (platform, )), uzdir)
            with open( os.path.join(tdir, "dist", "eskytester-0.3.%s.from-0.1.patch" % (platform, )), "rb") as f:
                esky.patch.apply_patch(uzdir, f)
            really_rmtree(uzdir)
            deep_extract_zipfile( os.path.join(tdir, "dist", "eskytester-0.2.%s.zip" % (platform, )), uzdir)
            with open( os.path.join(tdir, "dist", "eskytester-0.3.%s.from-0.2.patch" % (platform, )), "rb") as f:
                esky.patch.apply_patch(uzdir, f)
            really_rmtree(uzdir)

            #  Serve the updates at LOCAL_HTTP_PORT set in esky.util
            print("running local update server")
            try:
                server = HTTPServer(("localhost", LOCAL_HTTP_PORT), SimpleHTTPRequestHandler)
            except Exception:
                # in travis ci we start our own server
                pass
            else:
                server_thread = threading.Thread(target=server.serve_forever)
                server_thread.daemon = True
                server_thread.start()
            #  Set up the deployed esky environment for the initial version
            zfname = os.path.join(tdir, "dist",
                                  "eskytester-0.1.%s.zip" % (platform, ))
            os.mkdir(deploydir)
            extract_zipfile(zfname, deploydir)
            #  Run the scripts in order.
            if options["bdist_esky"]["freezer_module"] == "py2app":
                appdir = os.path.join(deploydir, os.listdir(deploydir)[0])
                cmd1 = os.path.join(appdir, "Contents", "MacOS", "script1")
                cmd2 = os.path.join(appdir, "Contents", "MacOS", "script2")
                cmd3 = os.path.join(appdir, "Contents", "MacOS", "script3")
            else:
                appdir = deploydir
                if sys.platform == "win32":
                    cmd1 = os.path.join(deploydir, "script1.exe")
                    cmd2 = os.path.join(deploydir, "script2.exe")
                    cmd3 = os.path.join(deploydir, "script3.exe")
                else:
                    cmd1 = os.path.join(deploydir, "script1")
                    cmd2 = os.path.join(deploydir, "script2")
                    cmd3 = os.path.join(deploydir, "script3")
            print("spawning eskytester script1", options["bdist_esky"][ "freezer_module"])
            os.unlink(os.path.join(tdir, "dist", "eskytester-0.1.%s.zip" % (
                platform, )))

            p = subprocess.Popen(cmd1)
            if p.wait():
                print(p.stdout)
                print(p.stderr)
                assert False
            os.unlink(os.path.join(appdir,"tests-completed"))

            print("spawning eskytester script2")
            os.unlink(os.path.join(tdir, "dist", "eskytester-0.2.%s.zip" % (
                platform, )))
            p = subprocess.Popen(cmd2)
            if p.wait():
                print(p.stdout)
                print(p.stderr)
                assert False
            os.unlink(os.path.join(appdir,"tests-completed"))

            print("spawning eskytester script3")
            p = subprocess.Popen(cmd3)
            if p.wait():
                print(p.stdout)
                print(p.stderr)
                assert False
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
            vdir = os.path.join(appdir, ESKY_APPDATA_DIR,
                                "testapp-0.1.%s" % (platform,))
            os.makedirs(vdir)
            os.mkdir(os.path.join(vdir, ESKY_CONTROL_DIR))
            open( os.path.join(vdir, ESKY_CONTROL_DIR, "bootstrap-manifest.txt"), "wb").close()
            e1 = esky.Esky(appdir, "http://example.com/downloads/")
            assert e1.name == "testapp"
            assert e1.version == "0.1"
            assert e1.platform == platform
            e2 = esky.Esky(appdir, "http://example.com/downloads/")
            assert e2.name == "testapp"
            assert e2.version == "0.1"
            assert e2.platform == platform
            locked = []
            errors = []
            trigger1 = threading.Event()
            trigger2 = threading.Event()

            def runit(e, t1, t2):
                def runme():
                    try:
                        e.lock()
                    except Exception as err:
                        errors.append(err)
                    else:
                        locked.append(e)
                    t1.set()
                    t2.wait()

                return runme

            t1 = threading.Thread(target=runit(e1, trigger1, trigger2))
            t2 = threading.Thread(target=runit(e2, trigger2, trigger1))
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            assert len(locked) == 1
            assert (e1 in locked or e2 in locked)
            assert len(errors) == 1
            assert isinstance(errors[0], esky.EskyLockedError)
        finally:
            really_rmtree(appdir)

    def test_esky_lock_breaking(self):
        """Test that breaking the lock on an Esky works correctly."""
        appdir = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(appdir, ESKY_APPDATA_DIR, "testapp-0.1",
                                     ESKY_CONTROL_DIR))
            open( os.path.join(appdir, ESKY_APPDATA_DIR, "testapp-0.1", ESKY_CONTROL_DIR, "bootstrap-manifest.txt"), "wb").close()
            e1 = esky.Esky(appdir, "http://example.com/downloads/")
            e2 = esky.Esky(appdir, "http://example.com/downloads/")
            trigger1 = threading.Event()
            trigger2 = threading.Event()
            errors = []

            def run1():
                try:
                    e1.lock()
                except Exception as err:
                    errors.append(err)
                trigger1.set()
                trigger2.wait()

            def run2():
                trigger1.wait()
                try:
                    e2.lock()
                except esky.EskyLockedError:
                    pass
                except Exception as err:
                    errors.append(err)
                else:
                    errors.append("locked when I shouldn't have")
                e2.lock_timeout = 0.1
                time.sleep(0.5)
                try:
                    e2.lock()
                except Exception as err:
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
            really_rmtree(appdir)


class TestFSTransact(unittest.TestCase):
    """Testcases for FSTransact."""

    def setUp(self):
        self.testdir = tempfile.mkdtemp()

    def tearDown(self):
        really_rmtree(self.testdir)

    def path(self, path):
        return os.path.join(self.testdir, path)

    def setContents(self, path, contents=""):
        if not os.path.isdir(os.path.dirname(self.path(path))):
            os.makedirs(os.path.dirname(self.path(path)))
        with open(self.path(path), "wb") as f:
            f.write(contents.encode())

    def assertContents(self, path, contents):
        with open(self.path(path), "rb") as f:
            self.assertEquals(f.read().decode(), contents)

    def test_no_move_outside_root(self):
        self.setContents("file1", "hello world")
        trn = FSTransaction(self.testdir)
        trn.move(self.path("file1"), "file2")
        trn.commit()
        self.assertContents("file2", "hello world")
        trn = FSTransaction(self.testdir)
        self.assertRaises(ValueError, trn.move, self.path("file2"), "../file1")
        trn.abort()

    def test_move_file(self):
        self.setContents("file1", "hello world")
        trn = FSTransaction()
        trn.move(self.path("file1"), self.path("file2"))
        self.assertContents("file1", "hello world")
        self.assertFalse(os.path.exists(self.path("file2")))
        trn.commit()
        self.assertContents("file2", "hello world")
        self.assertFalse(os.path.exists(self.path("file1")))

    def test_move_file_with_unicode_name(self):
        self.setContents(u"file\N{SNOWMAN}", "hello world")
        trn = FSTransaction()
        trn.move(self.path(u"file\N{SNOWMAN}"), self.path("file2"))
        self.assertContents(u"file\N{SNOWMAN}", "hello world")
        self.assertFalse(os.path.exists(self.path("file2")))
        trn.commit()
        self.assertContents("file2", "hello world")
        self.assertFalse(os.path.exists(self.path(u"file\N{SNOWMAN}")))

    def test_copy_file(self):
        self.setContents("file1", "hello world")
        trn = FSTransaction()
        trn.copy(self.path("file1"), self.path("file2"))
        self.assertContents("file1", "hello world")
        self.assertFalse(os.path.exists(self.path("file2")))
        trn.commit()
        self.assertContents("file1", "hello world")
        self.assertContents("file2", "hello world")

    def test_move_dir(self):
        self.setContents("dir1/file1", "hello world")
        self.setContents("dir1/file2", "how are you?")
        self.setContents("dir1/subdir/file3", "fine thanks")
        trn = FSTransaction()
        trn.move(self.path("dir1"), self.path("dir2"))
        self.assertContents("dir1/file1", "hello world")
        self.assertFalse(os.path.exists(self.path("dir2")))
        trn.commit()
        self.assertContents("dir2/file1", "hello world")
        self.assertContents("dir2/file2", "how are you?")
        self.assertContents("dir2/subdir/file3", "fine thanks")
        self.assertFalse(os.path.exists(self.path("dir1")))

    def test_copy_dir(self):
        self.setContents("dir1/file1", "hello world")
        self.setContents("dir1/file2", "how are you?")
        self.setContents("dir1/subdir/file3", "fine thanks")
        trn = FSTransaction()
        trn.copy(self.path("dir1"), self.path("dir2"))
        self.assertContents("dir1/file1", "hello world")
        self.assertFalse(os.path.exists(self.path("dir2")))
        trn.commit()
        self.assertContents("dir2/file1", "hello world")
        self.assertContents("dir2/file2", "how are you?")
        self.assertContents("dir2/subdir/file3", "fine thanks")
        self.assertContents("dir1/file1", "hello world")
        self.assertContents("dir1/file2", "how are you?")
        self.assertContents("dir1/subdir/file3", "fine thanks")

    def test_remove(self):
        self.setContents("dir1/file1", "hello there world")
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
        self.setContents("dir1/file1", "hello there world")
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
        self.setContents("dir1/file0", "zero zero zero")
        self.setContents("dir1/file1", "hello world")
        self.setContents("dir1/file2", "how are you?")
        self.setContents("dir1/subdir/file3", "fine thanks")
        self.setContents("dir2/file1", "different contents")
        self.setContents("dir2/file3", "a different file")
        self.setContents("dir1/subdir/file3", "fine thanks")
        trn = FSTransaction()
        trn.move(self.path("dir1"), self.path("dir2"))
        self.assertContents("dir1/file1", "hello world")
        trn.commit()
        self.assertContents("dir2/file0", "zero zero zero")
        self.assertContents("dir2/file1", "hello world")
        self.assertContents("dir2/file2", "how are you?")
        self.assertFalse(os.path.exists(self.path("dir2/file3")))
        self.assertContents("dir2/subdir/file3", "fine thanks")
        self.assertFalse(os.path.exists(self.path("dir1")))

    def test_copy_dir_exists(self):
        self.setContents("dir1/file0", "zero zero zero")
        self.setContents("dir1/file1", "hello world")
        self.setContents("dir1/file2", "how are you?")
        self.setContents("dir1/subdir/file3", "fine thanks")
        self.setContents("dir2/file1", "different contents")
        self.setContents("dir2/file3", "a different file")
        self.setContents("dir1/subdir/file3", "fine thanks")
        trn = FSTransaction()
        trn.copy(self.path("dir1"), self.path("dir2"))
        self.assertContents("dir1/file1", "hello world")
        trn.commit()
        self.assertContents("dir2/file0", "zero zero zero")
        self.assertContents("dir2/file1", "hello world")
        self.assertContents("dir2/file2", "how are you?")
        self.assertFalse(os.path.exists(self.path("dir2/file3")))
        self.assertContents("dir2/subdir/file3", "fine thanks")
        self.assertContents("dir1/file0", "zero zero zero")
        self.assertContents("dir1/file1", "hello world")
        self.assertContents("dir1/file2", "how are you?")
        self.assertContents("dir1/subdir/file3", "fine thanks")

    def test_move_dir_over_file(self):
        self.setContents("dir1/file0", "zero zero zero")
        self.setContents("dir2", "actually a file")
        trn = FSTransaction()
        trn.move(self.path("dir1"), self.path("dir2"))
        self.assertContents("dir1/file0", "zero zero zero")
        trn.commit()
        self.assertContents("dir2/file0", "zero zero zero")
        self.assertFalse(os.path.exists(self.path("dir1")))

    def test_copy_dir_over_file(self):
        self.setContents("dir1/file0", "zero zero zero")
        self.setContents("dir2", "actually a file")
        trn = FSTransaction()
        trn.copy(self.path("dir1"), self.path("dir2"))
        self.assertContents("dir1/file0", "zero zero zero")
        trn.commit()
        self.assertContents("dir2/file0", "zero zero zero")
        self.assertContents("dir1/file0", "zero zero zero")

    def test_move_file_over_dir(self):
        self.setContents("file0", "zero zero zero")
        self.setContents("dir2/myfile", "hahahahaha!")
        trn = FSTransaction()
        trn.move(self.path("file0"), self.path("dir2"))
        self.assertContents("file0", "zero zero zero")
        self.assertContents("dir2/myfile", "hahahahaha!")
        trn.commit()
        self.assertContents("dir2", "zero zero zero")
        self.assertFalse(os.path.exists(self.path("file0")))

    def test_copy_file_over_dir(self):
        self.setContents("file0", "zero zero zero")
        self.setContents("dir2/myfile", "hahahahaha!")
        trn = FSTransaction()
        trn.copy(self.path("file0"), self.path("dir2"))
        self.assertContents("file0", "zero zero zero")
        self.assertContents("dir2/myfile", "hahahahaha!")
        trn.commit()
        self.assertContents("dir2", "zero zero zero")
        self.assertContents("file0", "zero zero zero")


class TestPatch(unittest.TestCase):
    """Testcases for esky.patch."""

    _TEST_FILES = (
        ("pyenchant-1.2.0.tar.gz", "2fefef0868b110b1da7de89c08344dd2"),
        ("pyenchant-1.5.2.tar.gz", "fa1e4f3f3c473edd98c7bb0e46eea352"),
        ("pyenchant-1.6.0.tar.gz", "3fd7336989764d8d379a367236518439"), )

    _TEST_FILES_URL = "http://pypi.python.org/packages/source/p/pyenchant/"

    def setUp(self):
        self.tests_root = dirname(__file__)
        platform = get_platform()
        self.tfdir = tfdir = os.path.join(self.tests_root, "patch-test-files")
        self.workdir = workdir = os.path.join(self.tests_root,
                                              "patch-test-temp." + platform)
        if not os.path.isdir(tfdir):
            os.makedirs(tfdir)
        if os.path.isdir(workdir):
            really_rmtree(workdir)
        os.makedirs(workdir)
        self.src_dir = os.path.join(workdir, 'source')
        self.tgt_dir = os.path.join(workdir, 'target')
        #  Ensure we have the expected test files.
        #  Download from PyPI if necessary.
        for (tfname, hash) in self._TEST_FILES:
            tfpath = os.path.join(tfdir, tfname)
            if not os.path.exists(tfpath):
                data = urllib.request.urlopen(self._TEST_FILES_URL + tfname).read()
                assert hashlib.md5(data).hexdigest() == hash
                with open(tfpath, "wb") as f:
                    f.write(data)

    def tearDown(self):
        really_rmtree(self.workdir)

    def test_patch_bigfile(self):
        tdir = tempfile.mkdtemp()
        try:
            data = [os.urandom(100) * 10 for i in range(6)]
            for nm in ("source", "target"):
                with open(os.path.join(tdir, nm), "wb") as f:
                    for i in range(1000):
                        for chunk in data:
                            f.write(chunk)
                data[2], data[3] = data[3], data[2]
            with open(os.path.join(tdir, "patch"), "wb") as f:
                esky.patch.write_patch(
                    os.path.join(tdir,
                                 "source"), os.path.join(tdir, "target"), f)
            dgst1 = esky.patch.calculate_digest(os.path.join(tdir, "target"))
            dgst2 = esky.patch.calculate_digest(os.path.join(tdir, "source"))
            self.assertNotEquals(dgst1, dgst2)
            with open(os.path.join(tdir, "patch"), "rb") as f:
                esky.patch.apply_patch(os.path.join(tdir, "source"), f)
            dgst3 = esky.patch.calculate_digest(os.path.join(tdir, "source"))
            self.assertEquals(dgst1, dgst3)
        finally:
            really_rmtree(tdir)

    def test_diffing_back_and_forth(self):
        for (tf1, _) in self._TEST_FILES:
            for (tf2, _) in self._TEST_FILES:
                path1, path2 = self._extract(tf1, tf2)
                with open(os.path.join(self.workdir, "patch"), "wb") as f:
                    esky.patch.write_patch(path1, path2, f)
                if tf1 != tf2:
                    self.assertNotEquals(
                        esky.patch.calculate_digest(path1),
                        esky.patch.calculate_digest(path2))
                with open(os.path.join(self.workdir, "patch"), "rb") as f:
                    esky.patch.apply_patch(path1, f)
                self.assertEquals(
                    esky.patch.calculate_digest(path1),
                    esky.patch.calculate_digest(path2))

    def test_apply_patch_old(self):
        '''uses the old method which calculates the digest for the entire
        folder when comparing, application has no filelist'''
        path1, path2 = self._extract("pyenchant-1.2.0.tar.gz",
                                     "pyenchant-1.6.0.tar.gz")
        path1 = os.path.join(path1, "pyenchant-1.2.0")
        path2 = os.path.join(path2, "pyenchant-1.6.0")
        pf = os.path.join(self.tfdir, "v1.2.0_to_v1.6.0.patch")
        if not os.path.exists(pf):
            pf = os.path.join(
                dirname(esky.__file__), "tests", "patch-test-files",
                "v1.2.0_to_v1.6.0.patch")
        with open(pf, "rb") as f:
            esky.patch.apply_patch(path1, f)
        self.assertEquals(
            esky.patch.calculate_digest(path1),
            esky.patch.calculate_digest(path2))

    def test_copying_multiple_targets_from_a_single_sibling(self):
        source = "movefrom-source.tar.gz"
        target = "movefrom-target.tar.gz"
        src_dir, tgt_dir = self._extract(source, target)

        # The two directory structures should initially be different.
        self.assertNotEquals(
            esky.patch.calculate_digest(src_dir),
            esky.patch.calculate_digest(tgt_dir))

        # Create patch from source to target.
        patch_fname = os.path.join(self.workdir, "patch")
        with open(patch_fname, "wb") as patchfile:
            esky.patch.write_patch(src_dir, tgt_dir, patchfile)

# Try to apply the patch.
        with open(patch_fname, "rb") as patchfile:
            esky.patch.apply_patch(src_dir, patchfile)

# Then the two directory structures should be equal.
        self.assertEquals(
            esky.patch.calculate_digest(src_dir),
            esky.patch.calculate_digest(tgt_dir))

    def _extract(self, source, target):
        '''extracts two tar gz files into a source and target dir which are returned'''
        if os.path.exists(self.src_dir):
            really_rmtree(self.src_dir)
        if os.path.exists(self.tgt_dir):
            really_rmtree(self.tgt_dir)
        f_source = tarfile.open(os.path.join(self.tfdir, source), "r:gz")
        f_target = tarfile.open(os.path.join(self.tfdir, target), "r:gz")
        try:
            f_source.extractall(self.src_dir)
            f_target.extractall(self.tgt_dir)
        finally:
            f_source.close()
            f_target.close()
        return self.src_dir, self.tgt_dir

    def test_apply_patch_with_filelist(self):
        '''Test applying patches where there is a filelist.
        Adds a file to the source and tries to apply the patch
        The digests of the folders should be different using calculate_digest
        but the same using calculate_patch_digest.
        This proves that the method with the filelist manifest works
        where the old method of digesting the whole folder, fails.'''
        source = "example-app-0.1.tar.gz"
        target = "example-app-0.2.tar.gz"
        src_dir, tgt_dir = self._extract(source, target)

        # we need to mock out the _cleanup_patch method because it will otherwise remove
        # any added files upon patching. In order to mock it out we
        # override the apply_patch function and pass it our custom Patcher where the
        #_cleanup_patch function has been neutralized.

        class EskyPatcher(esky.patch.Patcher):
            def _cleanup_patch(self):
                pass

        eskyApplyPatch = esky.patch.apply_patch

        def new_apply_patch(target, stream, **kwds):
            EskyPatcher(target, stream, **kwds).patch()

        esky.patch.apply_patch = new_apply_patch

        # The two directory structures should initially be different.
        self.assertNotEquals(
            esky.patch.calculate_patch_digest(src_dir),
            esky.patch.calculate_patch_digest(tgt_dir))

        # Create patch from source to target.
        patch_fname = os.path.join(self.workdir, "patch")
        with open(patch_fname, "wb") as patchfile:
            esky.patch.write_patch(src_dir, tgt_dir, patchfile)

        # Add file to source
        with open(os.path.join(src_dir, 'logfile.log'), 'w') as newfile:
            newfile.write('')

        # Try to apply the patch.
        with open(patch_fname, "rb") as patchfile:
            esky.patch.apply_patch(src_dir, patchfile)

        # Then the two directory structures should be different.
        self.assertNotEquals(
            esky.patch.calculate_digest(src_dir),
            esky.patch.calculate_digest(tgt_dir))

        # But using the filelist they should be equal
        self.assertEquals(
            esky.patch.calculate_patch_digest(src_dir),
            esky.patch.calculate_patch_digest(tgt_dir))

        # restore the apply_patch function
        esky.patch.apply_patch = eskyApplyPatch

    def test_apply_patch_with_filelist_removal_of_files_not_in_filelist(self):
        '''Test applying patches and cleaning up any files not in the filelist
        This works in the same way as the test_apply_patch_with_filelist
        Except now we don't mock out the _cleanup_patch method, and the directories
        should be identical after patching using the old or new method'''
        source = "example-app-0.1.tar.gz"
        target = "example-app-0.2.tar.gz"
        src_dir, tgt_dir = self._extract(source, target)
        print(src_dir, tgt_dir)

        # The two directory structures should initially be different.
        self.assertNotEquals(
            esky.patch.calculate_patch_digest(src_dir),
            esky.patch.calculate_patch_digest(tgt_dir))

        # Create patch from source to target.
        patch_fname = os.path.join(self.workdir, "patch")
        with open(patch_fname, "wb") as patchfile:
            esky.patch.write_patch(src_dir, tgt_dir, patchfile)

        # Add file to source
        with open(os.path.join(src_dir, 'logfile.log'), 'w') as newfile:
            newfile.write('')
        # Add pyc and pyo file
        with open(os.path.join(src_dir, 'python.pyc'), 'w') as newfile:
            newfile.write('')
        with open(os.path.join(src_dir, 'python.pyo'), 'w') as newfile:
            newfile.write('')

        # Apply the patch.
        with open(patch_fname, "rb") as patchfile:
            esky.patch.apply_patch(src_dir, patchfile)

        assert not os.path.exists(os.path.join(src_dir, 'python.pyc'))
        assert not os.path.exists(os.path.join(src_dir, 'python.pyo'))
        assert os.path.exists(os.path.join(src_dir, 'logfile.log'))

        os.remove(os.path.join(src_dir, 'logfile.log'))
        # Then the two directory structures should be the same.
        self.assertEquals(
            esky.patch.calculate_digest(src_dir),
            esky.patch.calculate_digest(tgt_dir))

    def _test_apply_patch_fail_when_sourcefile_has_been_deleted(self):
        '''Creates a patch between two versions, removes a file from
        the source and tries to apply patch. Should raise an exception'''
        source = "example-app-0.1.tar.gz"
        target = "example-app-0.2.tar.gz"
        src_dir, tgt_dir = self._extract(source, target)

        # The two directory structures should initially be different.
        self.assertNotEquals(
            esky.patch.calculate_patch_digest(src_dir),
            esky.patch.calculate_patch_digest(tgt_dir))

        # Create patch from source to target.
        patch_fname = os.path.join(self.workdir, "patch")
        with open(patch_fname, "wb") as patchfile:
            esky.patch.write_patch(src_dir, tgt_dir, patchfile)

        # Remove file from source
        os.remove(os.path.join(src_dir, 'example.exe'))

        # Try to apply the patch.
        with open(patch_fname, "rb") as patchfile:
            esky.patch.apply_patch(src_dir, patchfile)


    # should have failed by now...
    def test_apply_patch_fail_when_sourcefile_has_been_deleted(self):
        with pytest.raises(Exception):
            self._test_apply_patch_fail_when_sourcefile_has_been_deleted()


class TestPatch_cxbsdiff(TestPatch):
    """Test the patching code with cx-bsdiff rather than bsdiff4."""

    def setUp(self):
        self.__orig_bsdiff4 = esky.patch.bsdiff4
        if esky.patch.bsdiff4_cx is not None:
            esky.patch.bsdiff4 = esky.patch.bsdiff4_cx
        return super(TestPatch_cxbsdiff, self).setUp()

    def tearDown(self):
        esky.patch.bsdiff4 = self.__orig_bsdiff4
        return super(TestPatch_cxbsdiff, self).tearDown()


class TestPatch_pybsdiff(TestPatch):
    """Test the patching code with pure-python bsdiff4."""

    def setUp(self):
        self.__orig_bsdiff4 = esky.patch.bsdiff4
        esky.patch.bsdiff4 = esky.patch.bsdiff4_py
        return super(TestPatch_pybsdiff, self).setUp()

    def tearDown(self):
        esky.patch.bsdiff4 = self.__orig_bsdiff4
        return super(TestPatch_pybsdiff, self).tearDown()


class TestFilesDiffer(unittest.TestCase):
    def setUp(self):
        self.tdir = tempfile.mkdtemp()

    def _path(self, *names):
        return os.path.join(self.tdir, *names)

    def _differs(self, data1, data2, start=0, stop=None):
        with open(self._path("file1"), "wb") as f:
            f.write(data1.encode("ascii"))
        with open(self._path("file2"), "wb") as f:
            f.write(data2.encode("ascii"))
        return files_differ(
            self._path("file1"), self._path("file2"), start, stop)

    def test_files_differ(self):
        assert self._differs("one", "two")
        assert self._differs("onethreetwo", "twothreeone")
        assert self._differs("onethreetwo", "twothreeone", 3)
        assert not self._differs("onethreetwo", "twothreeone", 3, -3)
        assert self._differs("onethreetwo", "twothreeone", 2, -3)
        assert self._differs("onethreetwo", "twothreeone", 3, -2)

    def tearDown(self):
        really_rmtree(self.tdir)

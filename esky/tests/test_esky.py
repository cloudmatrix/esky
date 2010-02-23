
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
import time
from SimpleHTTPServer import SimpleHTTPRequestHandler
from BaseHTTPServer import HTTPServer

from distutils.core import setup as dist_setup
from distutils import dir_util

import esky
from esky import bdist_esky
from esky.util import extract_zipfile, get_platform
from esky.fstransact import FSTransaction

try:
    import bbfreeze
except ImportError:
    bbfreeze = None
try:
    import py2exe
except ImportError:
    py2exe = None
try:
    import cx_Freeze
except ImportError:
    cx_Freeze = None

sys.path.append(os.path.dirname(__file__))


if not hasattr(HTTPServer,"shutdown"):
    import socket
    def socketserver_shutdown(self):
        try:
            self.socket.close()
        except socket.error:
            pass
    HTTPServer.shutdown = socketserver_shutdown


class TestEsky(unittest.TestCase):

  if bbfreeze is not None:
    def test_esky_bbfreeze(self):
        """Build and launch a self-testing esky application using bbfreeze."""
        self._run_eskytester({"bdist_esky":{"freezer_module":"bbfreeze"}})

  if py2exe is not None:
    def test_esky_py2exe(self):
        """Build and launch a self-testing esky application using py2exe."""
        self._run_eskytester({"bdist_esky":{"freezer_module":"py2exe"}})

  if cx_Freeze is not None:
    def test_esky_cxfreeze(self):
        """Build and launch a self-testing esky application using cx_Freeze."""
        self._run_eskytester({"bdist_esky":{"freezer_module":"cxfreeze"}})

  def _run_eskytester(self,options):
    """Build and run the eskytester app using the given distutils options.

    The "eskytester" application can be found next to this file, and the
    sequence of tests performed range across "script1.py" to "script3.py".
    """
    olddir = os.path.abspath(os.curdir)
    server = None
    try:
        platform = get_platform()
        deploydir = "deploy.%s" % (platform,)
        esky_root = dirname(dirname(dirname(__file__)))
        os.chdir(os.path.join(esky_root,"esky","tests"))
        #  Clean up after previous test runs.
        if os.path.isdir(deploydir):
            shutil.rmtree(deploydir)
        for version in ("0.1","0.2","0.3"):
            build_dir = os.path.join("dist","eskytester-%s.%s")
            build_dir = build_dir % (version,platform,)
            if os.path.isdir(build_dir):
                shutil.rmtree(build_dir)
        dir_util._path_created.clear()
        #  Build three increasing versions of the test package.
        #  Version 0.2 will include a bundled MSVCRT on win32
        metadata = dict(name="eskytester",packages=["eskytester"],author="rfk",
                        description="the esky test package",
                        data_files=[("data",["eskytester/datafile.txt"])],
                        package_data={"eskytester":["pkgdata.txt"]},
                        script_args=["bdist_esky"])
        options2 = options.copy()
        options2["bdist_esky"] = options["bdist_esky"].copy()
        options2["bdist_esky"]["bundle_msvcrt"] = True
        dist_setup(version="0.1",scripts=["eskytester/script1.py"],options=options,**metadata)
        dist_setup(version="0.2",scripts=["eskytester/script1.py","eskytester/script2.py"],options=options2,**metadata)
        dist_setup(version="0.3",scripts=["eskytester/script2.py","eskytester/script3.py"],options=options,**metadata)
        #  Serve the updates at http://localhost:8000/dist/
        print "running local update server"
        server = HTTPServer(("localhost",8000),SimpleHTTPRequestHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        #  Set up the deployed esky environment for the initial version
        zfname = os.path.join("dist","eskytester-0.1.%s.zip"%(platform,))
        os.mkdir(deploydir)
        extract_zipfile(zfname,deploydir)
        #  Run the first script, which will perform the necessary tests,
        #  launch script2 and script3, and write the file "tests-completed".
        if os.path.exists("tests-completed"):
            os.unlink("tests-completed")
        if sys.platform == "win32":
            cmd = os.path.join(deploydir,"script1.exe")
        else:
            cmd = os.path.join(deploydir,"script1")
        print "spawning eskytester application"
        p = subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (stdout,_) = p.communicate()
        sys.stdout.write(stdout.decode())
        assert p.returncode == 0
        assert os.path.exists("tests-completed")
        os.unlink("tests-completed")
    finally:
        os.chdir(olddir)
        if server:
            server.shutdown()

 
  def test_esky_locking(self):
    """Test that locking an Esky works correctly."""
    platform = get_platform()
    appdir = tempfile.mkdtemp()
    try: 
        vdir = os.path.join(appdir,"testapp-0.1.%s" % (platform,))
        os.mkdir(vdir)
        open(os.path.join(vdir,"esky-bootstrap.txt"),"wb").close()
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
        os.mkdir(os.path.join(appdir,"testapp-0.1"))
        open(os.path.join(appdir,"testapp-0.1","esky-bootstrap.txt"),"wb").close()
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
    readme = os.path.join(dirname(dirname(dirname(__file__))),"README.txt")
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


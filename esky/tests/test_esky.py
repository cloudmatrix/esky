
import sys
import difflib
import os
from os.path import dirname
import subprocess
import shutil
import zipfile
import threading
from SimpleHTTPServer import SimpleHTTPRequestHandler
from BaseHTTPServer import HTTPServer

from distutils.core import setup as dist_setup
from distutils.util import get_platform

import esky
from esky import bdist_esky


def test_esky():
    """Build and launch a simple self-testing esky application."""
    olddir = os.path.abspath(os.curdir)
    try:
        platform = get_platform()
        deploydir = "deploy"
        esky_root = dirname(dirname(dirname(__file__)))
        os.chdir(os.path.join(esky_root,"esky","tests"))
        if os.path.isdir(deploydir):
            shutil.rmtree(deploydir)
        #  Build three increasing versions of the test package
        metadata = dict(name="eskytester",packages=["eskytester"],author="rfk",
                        description="the esky test package",script_args=["bdist_esky"])
        dist_setup(version="0.1",scripts=["eskytester/script1.py"],**metadata)
        dist_setup(version="0.2",scripts=["eskytester/script1.py","eskytester/script2.py"],**metadata)
        dist_setup(version="0.3",scripts=["eskytester/script2.py","eskytester/script3.py"],**metadata)
        #  Serve the updates at http://localhost:8000/dist/
        server = HTTPServer(("localhost",8000),SimpleHTTPRequestHandler)
        threading.Thread(target=server.serve_forever).start()
        #  Set up the deployed esky environment for the initial version
        zfname = os.path.join("dist","eskytester-0.1.%s.zip"%(platform,))
        zf = zipfile.ZipFile(zfname,"r")
        os.mkdir(deploydir)
        for nm in zf.namelist():
            outfilenm = os.path.join(deploydir,nm)
            if not os.path.isdir(os.path.dirname(outfilenm)):
                os.makedirs(os.path.dirname(outfilenm))
            infile = zf.open(nm,"r")
            outfile = open(outfilenm,"wb")
            try:
                shutil.copyfileobj(infile,outfile)
            finally:
                infile.close()
                outfile.close()
            mode = zf.getinfo(nm).external_attr >> 16L
            os.chmod(outfilenm,mode)
        bsdir = os.path.join(deploydir,"eskytester-0.1","esky-bootstrap")
        for nm in os.listdir(bsdir):
            os.rename(os.path.join(bsdir,nm),os.path.join(deploydir,nm))
        os.rmdir(bsdir)
        #  Run the first script, which will perform the necessary tests
        #  and write "tests-completed" file when done.
        if os.path.exists("tests-completed"):
            os.unlink("tests-completed")
        if sys.platform == "win32":
            cmd = os.path.join(deploydir,"script1.exe")
        else:
            cmd = os.path.join(deploydir,"script1")
        p = subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (stdout,_) = p.communicate()
        sys.stdout.write(stdout)
        assert p.returncode == 0
        assert os.path.exists("tests-completed")
        os.unlink("tests-completed")
    finally:
        os.chdir(olddir)


def test_README():
    """Test that the README is in sync with the docstring."""
    dirname = os.path.dirname
    readme = os.path.join(dirname(dirname(dirname(__file__))),"README.txt")
    assert os.path.isfile(readme)
    diff = difflib.unified_diff(open(readme).readlines(),esky.__doc__.splitlines(True))
    diff = "".join(diff)
    if diff:
        print diff
        raise RuntimeError




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
import esky
from esky import bdist_esky


def test_esky():
    """Build and launch a simple self-testing esky application."""
    olddir = os.path.abspath(os.curdir)
    try:
        esky_root = dirname(dirname(dirname(__file__)))
        os.chdir(os.path.join(esky_root,"esky","tests"))
        if os.path.isdir("dist"):
            shutil.rmtree("dist")
        if os.path.isdir("downloads"):
            shutil.rmtree("downloads")
        #  Build three increasing versions of the test package
        metadata = dict(name="eskytester",packages=["eskytester"],author="rfk",
                        description="the esky test package",script_args=["bdist_esky"])
        dist_setup(version="0.1",scripts=["eskytester/script1.py"],**metadata)
        dist_setup(version="0.2",scripts=["eskytester/script1.py","eskytester/script2.py"],**metadata)
        dist_setup(version="0.3",scripts=["eskytester/script2.py","eskytester/script3.py"],**metadata)
        #  Package them as zipfiles for "download" by the test script
        os.mkdir("downloads")
        for ver in ("0.1","0.2","0.3"):
            distpath = os.path.join("dist","eskytester-%s"%(ver,))
            zfpath = os.path.join("downloads","eskytester-%s.zip"%(ver,))
            zf = zipfile.ZipFile(zfpath,"w")
            for (dirpath,dirnames,filenames) in os.walk(distpath):
                for fn in filenames:
                    fpath = os.path.join(dirpath,fn)
                    zpath = fpath[len(distpath):]
                    zf.write(fpath,zpath)
            zf.close()
        #  Serve the updates at http://localhost:8000/downloads/
        server = HTTPServer(("localhost",8000),SimpleHTTPRequestHandler)
        threading.Thread(target=server.serve_forever).start()
        #  Set up the esky environment for the initial version
        bsdir = os.path.join("dist","eskytester-0.1","esky-bootstrap")
        for nm in os.listdir(bsdir):
            os.rename(os.path.join(bsdir,nm),os.path.join("dist",nm))
        os.rmdir(bsdir)
        shutil.rmtree(os.path.join("dist","eskytester-0.2"))
        shutil.rmtree(os.path.join("dist","eskytester-0.3"))
        #  Run the first script, which will perform the necessary tests
        if sys.platform == "win32":
            cmd = os.path.join("dist","script1.exe")
        else:
            cmd = os.path.join("dist","script1")
        p = subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (stdout,_) = p.communicate()
        sys.stdout.write(stdout)
        assert p.returncode == 0
    finally:
        os.chdir(olddir)


def test_README():
    """Test that the README is in sync with the docstring."""
    dirname = os.path.dirname
    readme = os.path.join(dirname(dirname(dirname(__file__))),"README.txt")
    print readme
    assert os.path.isfile(readme)
    diff = difflib.unified_diff(open(readme).readlines(),esky.__doc__.splitlines(True))
    diff = "".join(diff)
    if diff:
        print diff
        raise RuntimeError




import sys
import os
from os.path import dirname
import subprocess

def test_esky():
    olddir = os.path.abspath(os.curdir)
    try:
        esky_root = dirname(dirname(dirname(__file__)))
        os.chdir(os.path.join(esky_root,"esky","tests"))
        if os.path.basename(sys.executable).startswith("python"):
            python = sys.executable
        else:
            python = "python"
        if "PYTHONPATH" in os.environ:
            pythonpath = os.environ["PYTHONPATH"]+os.pathsep+esky_root
        else:
            pythonpath = esky_root
        cmd = [python,"setup.py","bdist_esky"]
        assert subprocess.call(cmd,env={"PYTHONPATH":pythonpath}) == 0
    finally:
        os.chdir(olddir)



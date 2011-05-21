
import os
import sys
from HTMLParser import HTMLParser
import cPickle
import zipfile

def yes_i_am_working():
    """Check the the eskytester app is installed and available."""
    assert True

def yes_my_deps_are_working():
    """Check that dependencies have been correctly sucked in."""
    TestHTMLParser()

def yes_my_data_is_installed():
    """Check that datafiles have been correctly copied over."""
    if hasattr(sys,"frozen"):
        if sys.platform == "darwin":
            mydir = os.path.dirname(os.path.dirname(sys.executable))
            mydir = os.path.join(mydir,"Resources")
            assert os.path.exists(os.path.join(mydir,"data","datafile.txt"))
            pydir = "python%d.%d" % sys.version_info[:2]
            libfile = os.path.join(mydir,"lib",pydir,"site-packages.zip")
            lib = zipfile.ZipFile(libfile)
            assert "eskytester/pkgdata.txt" in lib.namelist()
        else:
            mydir = os.path.join(os.path.dirname(sys.executable))
            assert os.path.exists(os.path.join(mydir,"data","datafile.txt"))
            try:
                lib = zipfile.ZipFile(os.path.join(mydir,"library.zip"))
                assert "eskytester/pkgdata.txt" in lib.namelist()
            except IOError:
                pkgdata = os.path.join(mydir,"eskytester","pkgdata.txt")
                assert os.path.exists(pkgdata)
    else:
        mydir = os.path.dirname(__file__)
        assert os.path.exists(os.path.join(mydir,"datafile.txt"))
        assert os.path.exists(os.path.join(mydir,"pkgdata.txt"))
    

class TestHTMLParser(HTMLParser):
   def __init__(self):
       HTMLParser.__init__(self)
       self.expecting = ["html","body","p","p"]
       self.feed("<html><body><p>hi</p><p>world</p></body></html>")
   def handle_starttag(self,tag,attrs):
       assert tag == self.expecting.pop(0)


def script_path(app,script):
    if sys.platform == "win32":
        return (os.path.join(app.appdir,script+".exe"))
    elif sys.platform == "darwin":
        return (os.path.join(app.appdir,"Contents/MacOS",script))
    else:
        return (os.path.join(app.appdir,script))


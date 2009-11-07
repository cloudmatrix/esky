
#  Second entry point for testing an esky install.

import os
import sys
import stat
import esky
import esky.util
 

platform = esky.util.get_platform()
if sys.platform == "win32":
    dotexe = ".exe"
else:
    dotexe = ""

#  Check that the app is still working
import eskytester
eskytester.yes_i_am_working()
eskytester.yes_my_deps_are_working()
eskytester.yes_my_data_is_installed()

#  Sanity check the esky environment
assert sys.frozen
app = esky.Esky(sys.executable,"http://localhost:8000/dist/")
assert app.name == "eskytester"
assert app.version == "0.2"
assert app.find_update() == "0.3"
assert os.path.isfile(os.path.join(app.appdir,"script1"+dotexe))
assert os.path.isfile(os.path.join(app.appdir,"script2"+dotexe))

v3dir = os.path.join(app.appdir,"eskytester-0.3."+platform)
if len(sys.argv) == 1:
    app.cleanup()
    assert not os.path.isdir(os.path.join(app.appdir,"eskytester-0.1."+platform))
    assert not os.path.isdir(v3dir)
    script2 = os.path.join(app.appdir,"script2"+dotexe)
    #  Simulate a broken upgrade.
    app.version_finder.fetch_version("0.3")
    upv3 = app.version_finder.prepare_version("0.3")
    os.rename(upv3,v3dir)
    os.unlink(os.path.join(v3dir,"esky-bootstrap","script2"+dotexe))
    #  While we're here, check that the bootstrap library hasn't changed
    f1 = open(os.path.join(app.appdir,"library.zip"),"r")
    f2 = open(os.path.join(v3dir,"esky-bootstrap","library.zip"),"r")
    assert f1.read() == f2.read()
    f1.close()
    f2.close()
    #  Re-launch the script.
    #  We should still be at version 0.2 after this.
    os.execv(script2,[script2,"rerun"])
else:
    #  Recover from the broken upgrade
    assert len(sys.argv) == 2
    assert os.path.isdir(v3dir)
    app.install_update("0.3")
    assert not os.path.isfile(os.path.join(app.appdir,"script1"+dotexe))
    assert os.path.isfile(os.path.join(app.appdir,"script2"+dotexe))
    assert os.path.isfile(os.path.join(app.appdir,"script3"+dotexe))
    assert not os.path.isdir(os.path.join(app.appdir,"eskytester-0.1."+platform))
    assert not os.path.isfile(os.path.join(app.appdir,"eskytester-0.2."+platform,"library.zip"))
    assert os.path.isdir(os.path.join(app.appdir,"eskytester-0.3."+platform))
    script3 = os.path.join(app.appdir,"script3"+dotexe)
    os.execv(script3,[script3])



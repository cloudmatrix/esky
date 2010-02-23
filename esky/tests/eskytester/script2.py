
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

#  Test that MSVCRT was bundled correctly
if sys.platform == "win32":
    versiondir = os.path.dirname(sys.executable)
    for nm in os.listdir(versiondir):
        if nm.startswith("Microsoft.") and nm.endswith(".CRT"):
            msvcrt_dir = os.path.join(versiondir,nm)
            assert os.path.isdir(msvcrt_dir)
            assert len(os.listdir(msvcrt_dir)) >= 2
            break
    else:
        assert False, "MSVCRT not bundled in version dir"
    for nm in os.listdir(app.appdir):
        if nm.startswith("Microsoft.") and nm.endswith(".CRT"):
            msvcrt_dir = os.path.join(app.appdir,nm)
            assert os.path.isdir(msvcrt_dir)
            assert len(os.listdir(msvcrt_dir)) >= 2
            break
    else:
        assert False, "MSVCRT not bundled in app dir"


v3dir = os.path.join(app.appdir,"eskytester-0.3."+platform)
if len(sys.argv) == 1:
    app.cleanup()
    assert not os.path.isdir(os.path.join(app.appdir,"eskytester-0.1."+platform))
    assert not os.path.isdir(v3dir)
    script2 = os.path.join(app.appdir,"script2"+dotexe)
    #  Simulate a broken upgrade.
    upv3 = app.version_finder.fetch_version(app,"0.3")
    os.rename(upv3,v3dir)
    #  While we're here, check that the bootstrap library hasn't changed
    if os.path.exists(os.path.join(app.appdir,"library.zip")):
        f1 = open(os.path.join(app.appdir,"library.zip"),"r")
        f2 = open(os.path.join(v3dir,"esky-bootstrap","library.zip"),"r")
        assert f1.read() == f2.read()
        f1.close()
        f2.close()
        f1 = open(os.path.join(app.appdir,"script2"+dotexe),"r")
        f2 = open(os.path.join(v3dir,"esky-bootstrap","script2"+dotexe),"r")
        assert f1.read() == f2.read()
        f1.close()
        f2.close()
    os.unlink(os.path.join(v3dir,"esky-bootstrap","script2"+dotexe))
    #  Re-launch the script.
    #  We should still be at version 0.2 after this.
    os.execv(script2,[script2,"rerun"])
else:
    #  Recover from the broken upgrade
    assert len(sys.argv) == 2
    assert os.path.isdir(v3dir)
    app.auto_update()
    assert not os.path.isfile(os.path.join(app.appdir,"script1"+dotexe))
    assert os.path.isfile(os.path.join(app.appdir,"script2"+dotexe))
    assert os.path.isfile(os.path.join(app.appdir,"script3"+dotexe))
    assert not os.path.isdir(os.path.join(app.appdir,"eskytester-0.1."+platform))
    assert not os.path.isfile(os.path.join(app.appdir,"eskytester-0.2."+platform,"esky-bootstrap.txt"))
    assert os.path.isdir(os.path.join(app.appdir,"eskytester-0.3."+platform))
    script3 = os.path.join(app.appdir,"script3"+dotexe)
    os.execv(script3,[script3])



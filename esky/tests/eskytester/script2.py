
#  Second entry point for testing an esky install.

from __future__ import with_statement

import os
import sys
import stat
import subprocess
import esky
import esky.util
import esky.tests


ESKY_CONTROL_DIR = esky.util.ESKY_CONTROL_DIR
ESKY_APPDATA_DIR = esky.util.ESKY_APPDATA_DIR
 

platform = esky.util.get_platform()
if platform == "win32":
    import esky.winres
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
app = esky.tests.TestableEsky(sys.executable,"http://localhost:8000/dist/")
assert app.name == "eskytester"
assert app.active_version == app.version == "0.2"
assert app.find_update() == "0.3"
assert os.path.isfile(eskytester.script_path(app,"script1"))
assert os.path.isfile(eskytester.script_path(app,"script2"))

#  Test that MSVCRT was bundled correctly
if sys.platform == "win32" and sys.hexversion >= 0x20600000:
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

if ESKY_APPDATA_DIR:
    v1dir = os.path.join(os.path.dirname(app._get_versions_dir()),"eskytester-0.1."+platform)
else:
    v1dir = os.path.join(app._get_versions_dir(),"eskytester-0.1."+platform)
v3dir = os.path.join(app._get_versions_dir(),"eskytester-0.3."+platform)

if len(sys.argv) == 1:
    # This is the first time we've run this script.
    assert os.path.isdir(v1dir)
    assert not os.path.isdir(v3dir)
    if os.environ.get("ESKY_NEEDSROOT",""):
        app.get_root()
    app.cleanup()
    assert not os.path.isdir(v1dir)
    assert not os.path.isdir(v3dir)
    #  Check that the bootstrap env is intact
    with open(os.path.join(app._get_versions_dir(),"eskytester-0.2."+platform,ESKY_CONTROL_DIR,"bootstrap-manifest.txt"),"rt") as mf:
        for nm in mf:
            nm = nm.strip()
            assert os.path.exists(os.path.join(app.appdir,nm))
    script2 = eskytester.script_path(app,"script2")
    #  Simulate a broken upgrade.
    upv3 = app.version_finder.fetch_version(app,"0.3")
    os.rename(upv3,v3dir)
    #  While we're here, check that the bootstrap library hasn't changed
    if os.path.exists(os.path.join(app.appdir,"library.zip")):
        f1 = open(os.path.join(app.appdir,"library.zip"),"rb")
        f2 = open(os.path.join(v3dir,ESKY_CONTROL_DIR,"bootstrap","library.zip"),"rb")
        assert f1.read() == f2.read()
        f1.close()
        f2.close()
    #  Also check one of the bootstrap exes to make sure it has changed safely
    if sys.platform == "win32":
        f1 = open(os.path.join(app.appdir,"script2"+dotexe),"rb")
        f2 = open(os.path.join(v3dir,ESKY_CONTROL_DIR,"bootstrap","script2"+dotexe),"rb")
        if f1.read() != f2.read():
            assert esky.winres.is_safe_to_overwrite(f1.name,f2.name), "bootstrap exe was changed unsafely"
        f1.close()
        f2.close()
    if sys.platform == "darwin":
        os.unlink(os.path.join(v3dir,ESKY_CONTROL_DIR,"bootstrap/Contents/MacOS/script2"))
    elif sys.platform != "win32":
        # win32 won't let us delete it since we loaded it as a library
        # when checking whether it was safe to overwrite.
        os.unlink(os.path.join(v3dir,ESKY_CONTROL_DIR,"bootstrap","script2"+dotexe))
    #  Re-launch the script.
    #  We should still be at version 0.2 after this.
    subprocess.check_call([script2,"rerun"])
else:
    # This is the second time we've run this script.
    #  Recover from the broken upgrade
    assert len(sys.argv) == 2
    assert os.path.isdir(v3dir)
    assert os.path.isfile(eskytester.script_path(app,"script2"))
    app.auto_update()
    assert os.path.isfile(eskytester.script_path(app,"script2"))
    assert not os.path.isfile(eskytester.script_path(app,"script1"))
    assert os.path.isfile(eskytester.script_path(app,"script3"))
    assert os.path.isdir(os.path.join(app._get_versions_dir(),"eskytester-0.2."+platform))
    assert os.path.isdir(os.path.join(app._get_versions_dir(),"eskytester-0.3."+platform))

    open(os.path.join(app.appdir,"tests-completed"),"w").close()



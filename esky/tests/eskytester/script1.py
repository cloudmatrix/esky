
#  Entry point for testing an esky install.

import os
import sys
import time
import errno


import esky
import esky.tests
import esky.util

ESKY_CONTROL_DIR = esky.util.ESKY_CONTROL_DIR
ESKY_APPDATA_DIR = esky.util.ESKY_APPDATA_DIR

#  Test that the frozen app is actually working
import eskytester
eskytester.yes_i_am_working()
eskytester.yes_my_deps_are_working()
eskytester.yes_my_data_is_installed()

assert sys.frozen
assert __name__ == "__main__"
app = esky.tests.TestableEsky(sys.executable,"http://localhost:8000/dist/")
assert app.name == "eskytester"
assert app.active_version == "0.1"
assert app.version == "0.1"
assert app.find_update() == "0.3"
assert os.path.isfile(eskytester.script_path(app,"script1"))

#  Test that the script is executed with sensible globals etc, so
#  it can create classes and other "complicated" things
class ATestClass(object):
    def __init__(self):
        self.a = "A"
class BTestClass(ATestClass):
    def __init__(self):
        super(BTestClass,self).__init__()
        self.a = "B"
assert BTestClass().a == "B"


#  Spawn another instance that just busy-loops,
#  holding a lock on the current version.
if len(sys.argv) > 1:
    while True:
        time.sleep(0.1)
    sys.exit(0)
else:
    #  This needs to be in a function because of something screwy in the way
    #  py2exe (or our wrapper) execs the script.  It doesn't leave global
    #  variables alive long enough for atexit functions to find them.
    def spawn_busy_loop(app):
        import os
        import atexit
        import signal
        import ctypes
        import subprocess
        import eskytester
        proc = subprocess.Popen([eskytester.script_path(app,"script1"),"busyloop"])
        assert proc.poll() is None
        @atexit.register
        def cleanup():
            assert proc.poll() is None
            if hasattr(proc,"terminate"):
                proc.terminate()
            else:
               if sys.platform == "win32":
                  ctypes.windll.kernel32.TerminateProcess(int(proc._handle),-1)
               else:
                  os.kill(proc.pid,signal.SIGTERM)
            proc.wait()
    spawn_busy_loop(app)

#  Upgrade to the next version (0.2, even though 0.3 is available)
if os.environ.get("ESKY_NEEDSROOT",""):
    already_root = app.has_root()
    app.get_root()
    assert app.has_root()
    app.drop_root()
    assert app.has_root() == already_root
    app.get_root()


app.install_version("0.2")
app.reinitialize()
assert app.name == "eskytester"
assert app.active_version == "0.1"
assert app.version == "0.2"
assert app.find_update() == "0.3"


assert os.path.isfile(eskytester.script_path(app,"script1"))
assert os.path.isfile(eskytester.script_path(app,"script2"))
if ESKY_APPDATA_DIR:
    assert os.path.isfile(os.path.join(os.path.dirname(app._get_versions_dir()),"eskytester-0.1."+esky.util.get_platform(),ESKY_CONTROL_DIR,"bootstrap-manifest.txt"))
else:
    assert os.path.isfile(os.path.join(app._get_versions_dir(),"eskytester-0.1."+esky.util.get_platform(),ESKY_CONTROL_DIR,"bootstrap-manifest.txt"))
assert os.path.isfile(os.path.join(app._get_versions_dir(),"eskytester-0.2."+esky.util.get_platform(),ESKY_CONTROL_DIR,"bootstrap-manifest.txt"))


#  Check that we can't uninstall a version that's in use.
if ESKY_APPDATA_DIR:
    assert esky.util.is_locked_version_dir(os.path.join(os.path.dirname(app._get_versions_dir()),"eskytester-0.1."+esky.util.get_platform()))
else:
    assert esky.util.is_locked_version_dir(os.path.join(app._get_versions_dir(),"eskytester-0.1."+esky.util.get_platform()))
try:
    app.uninstall_version("0.1")
except esky.VersionLockedError:
    pass
else:
    assert False, "in-use version was not locked"

open(os.path.join(app.appdir,"tests-completed"),"w").close()

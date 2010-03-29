
#  Entry point for testing an esky install.

import os
import sys
import time

import esky
import esky.util

#  Test that the frozen app is actually working
import eskytester
eskytester.yes_i_am_working()
eskytester.yes_my_deps_are_working()
eskytester.yes_my_data_is_installed()

assert sys.frozen
app = esky.Esky(sys.executable,"http://localhost:8000/dist/")
assert app.name == "eskytester"
assert app.active_version == "0.1"
assert app.version == "0.1"
assert app.find_update() == "0.3"
assert os.path.isfile(eskytester.script_path(app,"script1"))

#  Spawn another instance that just busy-loops,
#  holding a lock on the current version.
sys.stderr.flush()
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
            if hasattr(proc,"terminate"):
                proc.terminate()
            else:
                if sys.platform == "win32":
                    ctypes.windll.kernel32.TerminateProcess(int(proc._handle),-1)
                else:
                    os.kill(proc.pid,signal.SIGTERM)
    spawn_busy_loop(app)

#  Upgrade to the next version (0.2, even though 0.3 is available)
app.install_version("0.2")
app.reinitialize()
assert app.name == "eskytester"
assert app.active_version == "0.1"
assert app.version == "0.2"
assert app.find_update() == "0.3"

assert os.path.isfile(eskytester.script_path(app,"script1"))
assert os.path.isfile(eskytester.script_path(app,"script2"))
assert os.path.isfile(os.path.join(app.appdir,"eskytester-0.1."+esky.util.get_platform(),"esky-bootstrap.txt"))
assert os.path.isfile(os.path.join(app.appdir,"eskytester-0.2."+esky.util.get_platform(),"esky-bootstrap.txt"))

#  Check that we can't uninstall a version that's in use.
try:
    app.uninstall_version("0.1")
except esky.VersionLockedError:
    pass
else:
    assert False, "in-use version was not locked"

if sys.platform == "darwin":
    open("../../../../tests-completed","w").close()
else:
    open("tests-completed","w").close()


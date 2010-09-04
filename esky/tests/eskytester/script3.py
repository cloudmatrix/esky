
#  Third entry point for testing an esky install.

import os
import sys
import time
import esky
import esky.util
import esky.tests

platform = esky.util.get_platform()

#  Test that the frozen app is actually working
import eskytester
eskytester.yes_i_am_working()
eskytester.yes_my_deps_are_working()
eskytester.yes_my_data_is_installed()

#  Test that we're at the best possible version
assert sys.frozen
app = esky.tests.TestableEsky(sys.executable,"http://localhost:8000/dist/")
assert app.name == "eskytester"
assert app.active_version == app.version == "0.3"
assert app.find_update() is None

if os.environ.get("ESKY_NEEDSROOT",""):
    app.get_root()

try:
    app.cleanup()
except esky.EskyLockedError:
    print "LOCKED, SLEEPING"
    time.sleep(10)
    app.cleanup()
assert os.path.isdir(os.path.join(app._get_versions_dir(),"eskytester-0.3."+platform))
assert not os.path.isfile(eskytester.script_path(app,"script1"))
assert os.path.isfile(eskytester.script_path(app,"script2"))
assert os.path.isfile(eskytester.script_path(app,"script3"))

#  Test that MSVCRT wasn't bundled with this version
if sys.platform == "win32":
    for nm in os.listdir(os.path.dirname(sys.executable)):
        if nm.startswith("Microsoft.") and nm.endswith(".CRT"):
            assert False, "MSVCRT bundled in version dir when it shouldn't be"
    for nm in os.listdir(app.appdir):
        if nm.startswith("Microsoft.") and nm.endswith(".CRT"):
            assert False, "MSVCRT bundled in appdir when it shouldn't be"

#  On windows, test that we were chainloaded without an execv
if sys.platform == "win32":
    if "ESKY_NO_CUSTOM_CHAINLOAD" not in os.environ:
        assert hasattr(sys,"bootstrap_executable"), "didn't chainload in-proc"


open(os.path.join(app.appdir,"tests-completed"),"w").close()

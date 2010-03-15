
#  Entry point for testing an esky install.

import os
import sys
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

#  Upgrade to the next version (0.2, even though 0.3 is available)
app.install_version("0.2")
app.reinitialize()
assert app.name == "eskytester"
assert app.active_version == "0.1"
assert app.version == "0.2"
assert app.find_update() == "0.3"

assert os.path.isfile(eskytester.script_path(app,"script1"))
assert os.path.isfile(eskytester.script_path(app,"script2"))
assert os.path.isdir(os.path.join(app.appdir,"eskytester-0.2."+esky.util.get_platform()))
script2 = eskytester.script_path(app,"script2")
os.execv(script2,[script2])


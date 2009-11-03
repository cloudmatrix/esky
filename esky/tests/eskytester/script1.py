
#  Entry point for testing an esky install.

import os
import sys
import esky

if sys.platform == "win32":
    dotexe = ".exe"
else:
    dotexe = ""

#  Test that the frozen app is actually working
import eskytester
eskytester.yes_i_am_working()
eskytester.yes_my_deps_are_working()

#  Upgrade to the next version (0.2, even though 0.3 is available)
assert sys.frozen
app = esky.Esky(sys.executable,"http://localhost:8000/dist/")
assert app.name == "eskytester"
assert app.version == "0.1"
assert app.find_update() == "0.3"
app.install_update("0.2")
assert app.name == "eskytester"
assert app.version == "0.2"
assert app.find_update() == "0.3"

assert os.path.isfile(os.path.join(app.appdir,"script1"+dotexe))
assert os.path.isfile(os.path.join(app.appdir,"script2"+dotexe))
assert os.path.isdir(os.path.join(app.appdir,"eskytester-0.2"))
script2 = os.path.join(app.appdir,"script2"+dotexe)
os.execv(script2,[script2])


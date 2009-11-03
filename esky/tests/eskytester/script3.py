
#  Third entry point for testing an esky install.

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

#  Test that we're at the best possible version
assert sys.frozen
app = esky.Esky(sys.executable,"http://localhost:8000/downloads/")
assert app.name == "eskytester"
assert app.version == "0.3"
assert app.find_update() is None


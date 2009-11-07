
#  Third entry point for testing an esky install.

import os
import sys
import esky
import esky.util

platform = esky.util.get_platform()
if sys.platform == "win32":
    dotexe = ".exe"
else:
    dotexe = ""

#  Test that the frozen app is actually working
import eskytester
eskytester.yes_i_am_working()
eskytester.yes_my_deps_are_working()
eskytester.yes_my_data_is_installed()

#  Test that we're at the best possible version
assert sys.frozen
app = esky.Esky(sys.executable,"http://localhost:8000/dist/")
assert app.name == "eskytester"
assert app.version == "0.3"
assert app.find_update() is None

app.cleanup()
assert not os.path.isdir(os.path.join(app.appdir,"eskytester-0.1."+platform))
assert not os.path.isdir(os.path.join(app.appdir,"eskytester-0.2."+platform))
assert os.path.isdir(os.path.join(app.appdir,"eskytester-0.3."+platform))

open("tests-completed","w").close()
print "TESTS COMPLETED"


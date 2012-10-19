import sys
from esky import bdist_esky
from distutils.core import setup

# for windows
# > python setup.py bdist_esky
if sys.platform in ['win32','cygwin','win64']:

    # Use bdist_esky instead of py2exe

    setup(
        name = "example-app",
        version = "0.1",
        #  All executables are listed in the "scripts" argument
        scripts = ["example.py"],
        options = {"bdist_esky": {
                  "freezer_module":"py2exe",
                }}
    )

# for mac
# > python setup.py bdist_esky
elif sys.platform == 'darwin':
    setup(
        name = "example-app",
        version = "0.1",
        scripts = ["example.py"],
        options = {"bdist_esky": {
                    "freezer_module":"py2app"
                 }}
    )

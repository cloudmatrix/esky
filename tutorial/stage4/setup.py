
import os, sys
from esky.bdist_esky import Executable
from distutils.core import setup

#  We can customuse the executable's creation by passing an instance
#  of Executable() instead of just the script name.
example = Executable("example.py",
            #  give our app the standard Python icon
            icon=os.path.join(sys.prefix,"DLLs","py.ico"),
            #  we could make the app gui-only by setting this to True
            gui_only=False,
            #  any other keyword args would be passed on to py2exe
          )

setup(
  name = "example-app",
  version = "0.4",
  scripts = [example],
  options = {"bdist_esky":{
               #  forcibly include some other modules
               "includes": ["SocketServer","email"],
               #  forcibly exclude some other modules
               "excludes": ["pydoc"],
               #  force esky to freeze the app using py2exe
               "freezer_module": "py2exe",
               #  tweak the options used by py2exe
               "freezer_options": {"bundle_files":3,"compressed":True},
            }},
)


import os, sys, time
from esky.bdist_esky import Executable
from distutils.core import setup
from glob import glob

subversion = 8

if sys.platform in ['win32','cygwin','win64']:

    data_files = [("images", glob(r'.\images\*.*'))]

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
      data_files=data_files,
      name = "example-app",
      version = "0.4.%d" % subversion,
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
              }}
    )

if sys.platform == 'darwin':

    data_files = [("images", glob(r'./images/*'))]
    app = ['example.py']

    example = Executable("example.py",
              #icon = os.path.join("images/box.icns"),
            )

    options = {
              "bdist_esky":{
                #  forcibly include some other modules
                "includes": [],
                #  forcibly exclude some other modules
                "excludes": ["pydoc"],
                #  force esky to freeze the app using py2exe
                "freezer_module": "py2app",
                #  tweak the options used by py2exe
                "freezer_options": {
                    "plist" : {
                      #"LSUIElement" : True,
                      #'CFBundleIdentifier': 'de.cloudmatrix.esky',
                      #'CFBundleIconFile' : 'images/box.icns',
                    }
                },
              }
            }

    setup(
        app=app,
        name = "example-app",
        version = "0.4.%d" % subversion,
        data_files=data_files,
        options=options,
        scripts = [example],
    )

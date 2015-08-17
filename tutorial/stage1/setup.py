import sys
from esky import bdist_esky
from distutils.core import setup

# for freezing with esky
# uncomment the block you want to run depending on your freezer
# > python setup.py bdist_esky

# Using py2exe
#setup(
#    name = "example-app",
#    version = "0.1",
#    scripts = ["example.py"],
#    options = {"bdist_esky": {
#              "freezer_module":"py2exe",
#            }}
#)

# Using py2app
#setup(
#    name = "example-app",
#    version = "0.1",
#    scripts = ["example.py"],
#    options = {"bdist_esky": {
#                "freezer_module":"py2app"
#             }}
#    )

# cx freeze
from esky.bdist_esky import Executable
setup(
    name = 'example-app',
    version = '0.1',
   #executables=[Executable('example.py')],
    options = {"bdist_esky": {
                "freezer_module":"cxfreeze"
	      }},
    scripts = [Executable('example.py')],
)


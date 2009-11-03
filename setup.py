
from distutils.core import setup

import esky

NAME = "esky"
VERSION = esky.__version__
DESCRIPTION = "keep frozen apps fresh"
AUTHOR = "Ryan Kelly"
AUTHOR_EMAIL = "rfk@cloud.me"
URL = "http://github.com/clouddotme/esky/"
LICENSE = "BSD"
KEYWORDS = "update auto-update freeze"
LONG_DESC = esky.__doc__

PACKAGES = ["esky"]
EXT_MODULES = []
PKG_DATA = {}

setup(name=NAME,
      version=VERSION,
      author=AUTHOR,
      author_email=AUTHOR_EMAIL,
      url=URL,
      description=DESCRIPTION,
      long_description=LONG_DESC,
      keywords=KEYWORDS,
      packages=PACKAGES,
      ext_modules=EXT_MODULES,
      package_data=PKG_DATA,
      license=LICENSE,
      test_suite="nose.collector",
     )


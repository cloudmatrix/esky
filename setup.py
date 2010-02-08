
import sys
setup_kwds = {}
try:
    from setuptools import setup
    setup_kwds["test_suite"] = "esky.tests.test_esky"
    if sys.version_info > (3,):
        setup_kwds["use_2to3"] = True
except ImportError:
    from distutils.core import setup


try:
    next = next
except NameError:
    def next(i):
        return i.next()


info = {}
try:
    src = open("esky/__init__.py")
    lines = []
    ln = next(src)
    while "__version__" not in ln:
        lines.append(ln)
        ln = next(src)
    while "__version__" in ln:
        lines.append(ln)
        ln = next(src)
    exec("".join(lines),info)
except Exception:
    pass


NAME = "esky"
VERSION = info["__version__"]
DESCRIPTION = "keep frozen apps fresh"
AUTHOR = "Ryan Kelly"
AUTHOR_EMAIL = "rfk@cloud.me"
URL = "http://github.com/clouddotme/esky/"
LICENSE = "BSD"
KEYWORDS = "update auto-update freeze"
LONG_DESC = info["__doc__"]

PACKAGES = ["esky","esky.bdist_esky","esky.tests","esky.tests.eskytester"]
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
      **setup_kwds
     )


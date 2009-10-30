"""

  esky:  easy management and distribution of frozen python apps

This package provides a wrapper around bbfreeze to help manage frozen python
applications.  Currently it provides an easy auto-update mechanism.

"""

__ver_major__ = 0
__ver_minor__ = 1
__ver_patch__ = 0
__ver_sub__ = ""
__version__ = "%d.%d.%d%s" % (__ver_major__,__ver_minor__,
                              __ver_patch__,__ver_sub__)


import sys
import os

from esky.errors import *


def get_current():
    """Get the current Esky, or None if not frozen."""
    if sys.frozen:
        try:
            return Esky(os.path.dirname(sys.executable))
        except BrokenEskyError:
            return None
    else:
        return None


class Esky(object):
    """Class representing a packaged frozen app."""

    def __init__(self,appdir):
        self.appdir = appdir


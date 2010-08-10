#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.fstransact: best-effort support for transactional filesystem operations

This module provides a uniform interface to various platform-specific 
mechanisms for doing transactional filesystem operations.  On platforms where
transactions are not supported, it falls back to doing things one operation
at a time.

Currently supported platforms are:

    * Windows Vista and later, using MoveFileTransacted and friends
    * err..that's it for the moment, actually

Although transactions are not supported on POSIX platforms, the way Esky
structures its filesystem operations means that the program is always safe
as long as you can atomically replace a file.

"""

import os
import sys
import shutil

from esky.util import lazy_import


@lazy_import
def _fallback():
    import esky.fstransact.fallback
    return esky.fstransact.fallback

@lazy_import
def _win32txf():
    try:
        import esky.fstransact.win32txf
    except ImportError:
        return None
    else:
        return esky.fstransact.win32txf


def FSTransaction(root=None):
    """Factory function returning FSTransaction objects.

    This factory function takes the root path within which file operations
    will be performed, and returns an appropriate FSTransaction object that
    provides best-effort transactional operations for that root.
    """
    #  Try to use TxF on win32.  This might fail because it's not available,
    #  or because the target filesystem doesn't support it.
    if sys.platform == "win32" and _win32txf:
        try:
            return _win32txf.FSTransaction(root)
        except WindowsError, e:
            if e.winerror != _win32txf.ERROR_TRANSACTIONAL_OPEN_NOT_ALLOWED:
                raise
    #  If all else fails, use the fallback implementation.
    return _fallback.FSTransaction(root)



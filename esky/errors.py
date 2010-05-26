#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.errors:  error classes for esky

These definitions live in a separate sub-module to avoid circular imports,
but you should access them directly from the main 'esky' namespace.

"""

class Error(Exception):
    """Base error class for esky."""
    pass

class EskyBrokenError(Error):
    """Error thrown when accessing a broken esky directory."""
    pass

class EskyLockedError(Error):
    """Error thrown when trying to lock an esky that's already locked."""
    pass

class VersionLockedError(Error):
    """Error thrown when trying to remove a locked version."""
    pass

class EskyVersionError(Error):
    """Error thrown when an invalid version is requested."""
    pass

class NoVersionFinderError(Error):
    """Error thrown when trying to find updates without a VersionFinder."""
    pass



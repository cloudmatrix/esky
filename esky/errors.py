"""

  esky.errors:  error classes for esky

These definitions live in a separate sub-module to avoid circular imports,
but you should access them directly from the main 'esky' namespace.

"""




class Error(Exception):
    """Base error class for esky."""
    pass


class BrokenEskyError(Error):
    """Error thrown when accessing a broken esky directory."""
    pass

class NoSuchVersionError(Error):
    """Error thrown when an invalid version is requested."""
    pass



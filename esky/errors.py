
class Error(Exception):
    """Base errpr class for esky."""
    pass

class BrokenEskyError(Error):
    """Error thrown when accessing a broken esky directory."""
    pass


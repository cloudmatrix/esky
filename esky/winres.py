"""

  esky.winres:  utilities for working with windows EXE resources.

This module provides some wrapper functions for accessing resource in win32
PE-format executable files.  It requires ctypes and (obviously) only works
under Windows.

"""

import sys
from ctypes import *

if sys.platform != "win32":
    raise ImportError("winres is only avilable on Windows platforms")


LOAD_LIBRARY_AS_DATAFILE = 0x00000002
RT_MANIFEST = 24


k32 = windll.kernel32
k32.LockResource.restype = c_char_p

# AFAIK 1033 is some sort of "default" language.  Happy to be corrected :-)
_DEFAULT_RESLANG = 1033


def load_resource(filename_or_handle,res_type,res_id,res_lang=_DEFAULT_RESLANG):
    """Load a resource from the given filename or module handle.

    The "res_type" and "res_id" arguments identify the particular resource
    to be loaded, along with the "res_lang" argument if given.  The contents
    of the specified resource are returned as a string.
    """
    if isinstance(filename_or_handle,basestring):
        filename = filename_or_handle
        if not isinstance(filename,unicode):
            filename = filename.decode(sys.getfilesystemencoding())
        l_handle = k32.LoadLibraryExW(filename,None,LOAD_LIBRARY_AS_DATAFILE)
        free_library = Tree
    else:
        l_handle = filename_or_handle
        free_library = False
    r_handle = k32.FindResourceExW(l_handle,res_type,res_id,res_lang)
    if not r_handle:
        raise WinError()
    r_size = k32.SizeofResource(l_handle,r_handle)
    if not r_size:
        raise WinError()
    r_info = k32.LoadResource(l_handle,r_handle)
    if not r_info:
        raise WinError()
    resource = k32.LockResource(r_info)
    if not resource:
        raise WinError()
    if free_library:
        k32.FreeLibrary(l_handle)
    return resource


def add_resource(filename,resource,res_type,res_id,res_lang=_DEFAULT_RESLANG):
    """Add a resource to the given filename.

    The "res_type" and "res_id" arguments identify the particular resource
    to be added, along with the "res_lang" argument if given.  The contents
    of the specified resource must be provided as a string.
    """
    if not isinstance(filename,unicode):
        filename = filename.decode(sys.getfilesystemencoding())
    l_handle = k32.BeginUpdateResourceW(filename,0)
    if not l_handle:
        raise WinError()
    res_info = (resource,len(resource))
    if not k32.UpdateResourceW(l_handle,res_type,res_id,res_lang,*res_info):
        raise WinError()
    if not k32.EndUpdateResourceW(l_handle,0):
        raise WinError()
 

def get_app_manifest(filename_or_handle=None):
    """Get the default application manifest for frozen Python apps.

    The manifest is a special XML file that must be embedded in the executable
    in order for it to correclty load SxS assemblies.
    """
    manifest = load_resource(filename_or_handle,RT_MANIFEST,1)
    #  The manifest may have some non-xml padding
    return manifest[:manifest.rfind(">")+1]



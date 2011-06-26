"""

  esky.bdist_esky.pypy_winres:  access win32 exe resources in rpython


This module provides some functions for accessing win32 exe resources from
rpython code.  It's a trimmed-down version of the esky.winres module with
just enough functionality to get the py2exe compiled bootstrapper working.

"""

from pypy.rlib import clibffi
from pypy.rpython.lltypesystem import rffi, lltype
from pypy.rlib import rwin32


LOAD_LIBRARY_AS_DATAFILE = 0x00000002


k32_LoadLibraryExA = rwin32.winexternal("LoadLibraryExA",[rffi.CCHARP,rwin32.HANDLE,rwin32.DWORD],rwin32.HANDLE)
k32_FindResourceExA = rwin32.winexternal("FindResourceExA",[rwin32.HANDLE,rffi.CCHARP,rwin32.DWORD,rwin32.DWORD],rwin32.HANDLE)
k32_SizeofResource = rwin32.winexternal("SizeofResource",[rwin32.HANDLE,rwin32.HANDLE],rwin32.DWORD)
k32_LoadResource = rwin32.winexternal("LoadResource",[rwin32.HANDLE,rwin32.HANDLE],rwin32.HANDLE)
k32_LockResource = rwin32.winexternal("LockResource",[rwin32.HANDLE],rffi.CCHARP)
k32_FreeLibrary = rwin32.winexternal("FreeLibrary",[rwin32.HANDLE],rwin32.BOOL)


def load_resource(filename,resname,resid,reslang):
    """Load the named resource from the given file.

    The filename and resource name must be ascii strings, and the resid and
    reslang must be integers.
    """
    l_handle = k32_LoadLibraryExA(filename,rffi.cast(rwin32.HANDLE,0),LOAD_LIBRARY_AS_DATAFILE)
    if not l_handle:
        raise WindowsError(rwin32.GetLastError(),"LoadLibraryExW failed")
    try:
        r_handle = k32_FindResourceExA(l_handle,resname,resid,reslang)
        if not r_handle:
            raise WindowsError(rwin32.GetLastError(),"FindResourceExA failed")
        r_size = k32_SizeofResource(l_handle,r_handle)
        if not r_size:
            raise WindowsError(rwin32.GetLastError(),"SizeofResource failed")
        r_info = k32_LoadResource(l_handle,r_handle)
        if not r_info:
            raise WindowsError(rwin32.GetLastError(),"LoadResource failed")
        r_ptr = k32_LockResource(r_info)
        if not r_ptr:
            raise WindowsError(rwin32.GetLastError(),"LockResource failed")
        return rffi.charpsize2str(r_ptr,r_size)
    finally:
        if not k32_FreeLibrary(l_handle):
            raise WindowsError(rwin32.GetLastError(),"FreeLibrary failed")


def load_resource_pystr(py,filename,resname,resid,reslang):
    """Load the named resource from the given file as a python-level string

    The filename and resource name must be ascii strings, and the resid and
    reslang must be integers.

    This uses the given python dll object to load the data directly into 
    a python string, saving a lot of copying and carrying on.
    """
    l_handle = k32_LoadLibraryExA(filename,rffi.cast(rwin32.HANDLE,0),LOAD_LIBRARY_AS_DATAFILE)
    if not l_handle:
        raise WindowsError(rwin32.GetLastError(),"LoadLibraryExW failed")
    try:
        r_handle = k32_FindResourceExA(l_handle,resname,resid,reslang)
        if not r_handle:
            raise WindowsError(rwin32.GetLastError(),"FindResourceExA failed")
        r_size = k32_SizeofResource(l_handle,r_handle)
        if not r_size:
            raise WindowsError(rwin32.GetLastError(),"SizeofResource failed")
        r_info = k32_LoadResource(l_handle,r_handle)
        if not r_info:
            raise WindowsError(rwin32.GetLastError(),"LoadResource failed")
        r_ptr = k32_LockResource(r_info)
        if not r_ptr:
            raise WindowsError(rwin32.GetLastError(),"LockResource failed")
        s = py.String_FromStringAndSize(None,r_size)
        buf = py.String_AsString(s)
        memcpy(buf,rffi.cast(rffi.VOIDP,r_ptr),r_size)
        return s
    finally:
        if not k32_FreeLibrary(l_handle):
            raise WindowsError(rwin32.GetLastError(),"FreeLibrary failed")


def memcpy(target,source,n):
    impl = clibffi.CDLL(clibffi.get_libc_name()).getpointer("memcpy",[clibffi.ffi_type_pointer,clibffi.ffi_type_pointer,clibffi.ffi_type_uint],clibffi.ffi_type_void)
    impl.push_arg(target)
    impl.push_arg(source)
    impl.push_arg(n)
    impl.call(lltype.Void)
   


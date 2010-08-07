"""

    esky.bdist_esky.pypy_libpython:  load python DLL into pypy bootstrap exe


This module provides the class "libpython", an RPython-compatible class for
loading and exposing a python environment using libffi.  It's used by the
pypy-compiled bootstrap exes to bootstrap a version dir in-process.

"""


from pypy.rlib import libffi
from pypy.rpython.lltypesystem import rffi, lltype

class libpython:

    file_input = 257


    def __init__(self,library_path):
        self.lib = libffi.CDLL(library_path)


    def Initialize(self):
        impl = self.lib.getpointer("Py_Initialize",[],libffi.ffi_type_void)
        impl.call(lltype.Void)


    def Finalize(self):
        impl = self.lib.getpointer("Py_Finalize",[],libffi.ffi_type_void)
        impl.call(lltype.Void)


    def Err_Occurred(self):
        impl = self.lib.getpointer("PyErr_Occurred",[],libffi.ffi_type_pointer)
        return impl.call(rffi.VOIDP)


    def Err_PrintEx(self,set_sys_last_vars=1):
        impl = self.lib.getpointer("PyErr_PrintEx",[libffi.ffi_type_sint],libffi.ffi_type_void)
        impl.push_arg(set_sys_last_vars)
        return impl.call(lltype.Void)


    def _error(self):
        err = self.Err_Occurred()
        if err:
            self.Err_PrintEx()
            raise RuntimeError("an error occurred")


    def Run_SimpleString(self,string):
        impl = self.lib.getpointer("PyRun_SimpleString",[libffi.ffi_type_pointer],libffi.ffi_type_sint)
        buf = rffi.str2charp(string)
        impl.push_arg(buf)
        res = impl.call(rffi.INT)
        rffi.free_charp(buf)
        if res < 0:
            self._error()


    def Run_String(self,string,start,globals=None,locals=None):
        if globals is None:
            globals = 0
        if locals is None:
            locals = 0
        impl = self.lib.getpointer("PyRun_String",[libffi.ffi_type_pointer,libffi.ffi_type_sint,libffi.ffi_type_pointer,libffi.ffi_type_pointer],libffi.ffi_type_pointer)
        buf = rffi.str2charp(string)
        impl.push_arg(buf)
        impl.push_arg(start)
        impl.push_arg(globals)
        impl.push_arg(locals)
        res = impl.call(rffi.VOIDP)
        rffi.free_charp(buf)
        if not res:
            self._error()
        return res


    def GetProgramFullPath(self):
        impl = self.lib.getpointer("Py_GetProgramFullPath",[],libffi.ffi_type_pointer)
        return rffi.charp2str(impl.call(rffi.CCHARP))


    def SetPythonHome(self,path):
        impl = self.lib.getpointer("Py_SetPythonHome",[libffi.ffi_type_pointer],libffi.ffi_type_void)
        buf = rffi.str2charp(path)
        impl.push_arg(buf)
        impl.call(lltype.Void)
        rffi.free_charp(buf)


    # TODO: this seems to cause type errors during building
    def Sys_SetArgv(self,argv):
        impl = self.lib.getpointer("PySys_SetArgv",[libffi.ffi_type_sint,libffi.ffi_type_pointer],libffi.ffi_type_void)
        impl.push_arg(len(argv))
        buf = rffi.liststr2charpp(argv)
        impl.push_arg(rffi.cast(rffi.VOIDP,buf))
        impl.call(lltype.Void)
        rffi.free_charpp(buf)


    def Sys_SetPath(self,path):
        impl = self.lib.getpointer("PySys_SetPath",[libffi.ffi_type_pointer],libffi.ffi_type_void)
        buf = rffi.str2charp(path)
        impl.push_arg(buf)
        impl.call(lltype.Void)
        rffi.free_charp(buf)


    def Eval_GetBuiltins(self):
        impl = self.lib.getpointer("PyEval_GetBuiltins",[],libffi.ffi_type_pointer)
        d = impl.call(rffi.VOIDP)
        if not d:
            self._error()
        return d


    def Dict_New(self):
        impl = self.lib.getpointer("PyDict_New",[],libffi.ffi_type_pointer)
        d = impl.call(rffi.VOIDP)
        if not d:
            self._error()
        return d


    def Dict_SetItemString(self,d,key,value):
        impl = self.lib.getpointer("PyDict_SetItemString",[libffi.ffi_type_pointer,libffi.ffi_type_pointer,libffi.ffi_type_pointer],libffi.ffi_type_sint)
        impl.push_arg(d)
        buf = rffi.str2charp(key)
        impl.push_arg(buf)
        impl.push_arg(value)
        d = impl.call(rffi.INT)
        rffi.free_charp(buf)
        if d < 0:
            self._error()




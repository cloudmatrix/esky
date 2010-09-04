"""

    esky.bdist_esky.pypy_libpython:  load python DLL into pypy bootstrap exe


This module provides the class "libpython", an RPython-compatible class for
loading and exposing a python environment using libffi.  It's used by the
pypy-compiled bootstrap exes to bootstrap a version dir in-process.

"""


from pypy.rlib import libffi
from pypy.rpython.lltypesystem import rffi, lltype


class libpython(object):

    file_input = 257


    def __init__(self,library_path):
        self.lib = libffi.CDLL(library_path)
        self._libc = libffi.CDLL(libffi.get_libc_name())


    def Set_NoSiteFlag(self,value):
        addr = self.lib.getaddressindll("Py_NoSiteFlag")
        memset = self._libc.getpointer("memset",[libffi.ffi_type_pointer,libffi.ffi_type_uint,libffi.ffi_type_uint],libffi.ffi_type_void)
        memset.push_arg(addr)
        memset.push_arg(value)
        memset.push_arg(1)
        memset.call(lltype.Void)


    def Set_FrozenFlag(self,value):
        addr = self.lib.getaddressindll("Py_FrozenFlag")
        memset = self._libc.getpointer("memset",[libffi.ffi_type_pointer,libffi.ffi_type_uint,libffi.ffi_type_uint],libffi.ffi_type_void)
        memset.push_arg(addr)
        memset.push_arg(value)
        memset.push_arg(1)
        memset.call(lltype.Void)


    def Set_IgnoreEnvironmentFlag(self,value):
        addr = self.lib.getaddressindll("Py_IgnoreEnvironmentFlag")
        memset = self._libc.getpointer("memset",[libffi.ffi_type_pointer,libffi.ffi_type_uint,libffi.ffi_type_uint],libffi.ffi_type_void)
        memset.push_arg(addr)
        memset.push_arg(value)
        memset.push_arg(1)
        memset.call(lltype.Void)


    def Set_OptimizeFlag(self,value):
        addr = self.lib.getaddressindll("Py_OptimizeFlag")
        memset = self._libc.getpointer("memset",[libffi.ffi_type_pointer,libffi.ffi_type_uint,libffi.ffi_type_uint],libffi.ffi_type_void)
        memset.push_arg(addr)
        memset.push_arg(value)
        memset.push_arg(1)
        memset.call(lltype.Void)


    def Initialize(self):
        impl = self.lib.getpointer("Py_Initialize",[],libffi.ffi_type_void)
        impl.call(lltype.Void)


    def Finalize(self):
        impl = self.lib.getpointer("Py_Finalize",[],libffi.ffi_type_void)
        impl.call(lltype.Void)


    def Err_Occurred(self):
        impl = self.lib.getpointer("PyErr_Occurred",[],libffi.ffi_type_pointer)
        return impl.call(rffi.VOIDP)


    def Err_Print(self):
        impl = self.lib.getpointer("PyErr_Print",[],libffi.ffi_type_void)
        impl.call(lltype.Void)


    def _error(self):
        err = self.Err_Occurred()
        if err:
            self.Err_Print()
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


    def Import_ImportModule(self,name):
        impl = self.lib.getpointer("PyImport_ImportModule",[libffi.ffi_type_pointer],libffi.ffi_type_pointer)
        buf = rffi.str2charp(name)
        impl.push_arg(buf)
        mod = impl.call(rffi.VOIDP)
        rffi.free_charp(buf)
        if not mod:
            self._error()
        return mod


    def Object_GetAttr(self,obj,attr):
        impl = self.lib.getpointer("PyObject_GetAttr",[libffi.ffi_type_pointer,libffi.ffi_type_pointer],libffi.ffi_type_pointer)
        impl.push_arg(obj)
        impl.push_arg(attr)
        a = impl.call(rffi.VOIDP)
        if not a:
            self._error()
        return a


    def Object_GetAttrString(self,obj,attr):
        impl = self.lib.getpointer("PyObject_GetAttrString",[libffi.ffi_type_pointer,libffi.ffi_type_pointer],libffi.ffi_type_pointer)
        impl.push_arg(obj)
        buf = rffi.str2charp(attr)
        impl.push_arg(buf)
        a = impl.call(rffi.VOIDP)
        rffi.free_charp(buf)
        if not a:
            self._error()
        return a


    def Object_SetAttr(self,obj,attr,val):
        impl = self.lib.getpointer("PyObject_SetAttr",[libffi.ffi_type_pointer,libffi.ffi_type_pointer,libffi.ffi_type_pointer],libffi.ffi_type_sint)
        impl.push_arg(obj)
        impl.push_arg(attr)
        impl.push_arg(val)
        res = impl.call(rffi.INT)
        if res < 0:
            self._error()
        return None


    def Object_SetAttrString(self,obj,attr,val):
        impl = self.lib.getpointer("PyObject_SetAttrString",[libffi.ffi_type_pointer,libffi.ffi_type_pointer,libffi.ffi_type_pointer],libffi.ffi_type_sint)
        impl.push_arg(obj)
        buf = rffi.str2charp(attr)
        impl.push_arg(buf)
        impl.push_arg(val)
        res = impl.call(rffi.INT)
        rffi.free_charp(buf)
        if res < 0:
            self._error()
        return None


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


    def List_New(self,size=0):
        impl = self.lib.getpointer("PyList_New",[libffi.ffi_type_uint],libffi.ffi_type_pointer)
        impl.push_arg(size)
        l = impl.call(rffi.VOIDP)
        if not l:
            self._error()
        return l


    def List_Size(self,l):
        impl = self.lib.getpointer("PyList_Size",[libffi.ffi_type_pointer],libffi.ffi_type_uint)
        impl.push_arg(l)
        s = impl.call(rffi.INT)
        if s < 0:
            self._error()
        return s


    def List_SetItem(self,l,i,v):
        impl = self.lib.getpointer("PyList_SetItem",[libffi.ffi_type_pointer,libffi.ffi_type_uint,libffi.ffi_type_pointer],libffi.ffi_type_sint)
        impl.push_arg(l)
        impl.push_arg(i)
        impl.push_arg(v)
        res = impl.call(rffi.INT)
        if res < 0:
            self._error()


    def List_Append(self,l,v):
        impl = self.lib.getpointer("PyList_Append",[libffi.ffi_type_pointer,libffi.ffi_type_pointer],libffi.ffi_type_sint)
        impl.push_arg(l)
        impl.push_arg(v)
        res = impl.call(rffi.INT)
        if res < 0:
            self._error()


    def String_FromString(self,s):
        impl = self.lib.getpointer("PyString_FromString",[libffi.ffi_type_pointer],libffi.ffi_type_pointer)
        buf = rffi.str2charp(s)
        impl.push_arg(buf)
        ps = impl.call(rffi.VOIDP)
        rffi.free_charp(buf)
        if not ps:
            self._error()
        return ps


    def String_FromStringAndSize(self,s,size):
        impl = self.lib.getpointer("PyString_FromStringAndSize",[libffi.ffi_type_pointer,libffi.ffi_type_uint],libffi.ffi_type_pointer)
        if not s:
            buf = None
            impl.push_arg(None)
        else:
            buf = rffi.str2charp(s)
            impl.push_arg(buf)
        impl.push_arg(size)
        ps = impl.call(rffi.VOIDP)
        if s:
            rffi.free_charp(buf)
        if not ps:
            self._error()
        return ps


    def String_AsString(self,s):
        impl = self.lib.getpointer("PyString_AsString",[libffi.ffi_type_pointer],libffi.ffi_type_pointer)
        impl.push_arg(s)
        buf = impl.call(rffi.VOIDP)
        if not buf:
            self._error()
        return buf



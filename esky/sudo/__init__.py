#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.sudo:  spawn a root-privileged helper app to process esky updates.

This module provides the infrastructure for spawning a stand-alone "helper app"
to install updates with root privileges.  The class "SudoProxy" provides a
proxy to the methods of an object via a root-privileged helper process.

Example:

    app.install_version("1.2.3")
    -->   IOError:  permission denied

    sapp = SudoProxy(app)
    sapp.start()
    -->   prompts for credentials
    sapp.install_version("1.2.3")
    -->   success!


We also provide some handy utility functions:

    * has_root():      check whether current process has root privileges
    * can_get_root():  check whether current process may be able to get root
    


"""

from __future__ import absolute_import

import sys
import time

from esky.util import lazy_import

@lazy_import
def functools():
    import functools
    return functools

@lazy_import
def pickle():
    try:
       import cPickle as pickle
    except ImportError:
        import pickle
    return pickle

@lazy_import
def threading():
    try:
        import threading
    except ImportError:
        threading = None
    return threading


if sys.platform == "win32":
    @lazy_import
    def _impl():
        from esky.sudo import sudo_win32
        return sudo_win32
elif sys.platform == "darwin":
    @lazy_import
    def _impl():
        try:
            from esky.sudo import sudo_osx
            return sudo_osx
        except ImportError:
            from esky.sudo import sudo_unix
            return sudo_unix
else:
    @lazy_import
    def _impl():
        from esky.sudo import sudo_unix
        return sudo_unix


def spawn_sudo(proxy):
    return _impl.spawn_sudo(proxy)

def has_root():
    return _impl.has_root()

def can_get_root():
    return _impl.can_get_root()

def run_startup_hooks():
    if len(sys.argv) > 1 and sys.argv[1] == "--esky-spawn-sudo":
        return _impl.run_startup_hooks()


def b(data):
    """Like b"data", but valid syntax in older pythons as well.

    Sadly 2to3 can't get string constants right.
    """
    return data.encode("ascii")


class SudoProxy(object):
    """Object method proxy with root privileges.

    This class creates a copy of an object whose methods can be executed
    with root privileges.
    """

    def __init__(self,target):
        #  Reflect the 'name' attribute if it has one, but don't worry
        #  if not.  This helps SudoProxy be re-used on other classes.
        try:
            self.name = target.name
        except AttributeError:
            pass
        self.target = target
        self.closed = False
        self.pipe = None

    def start(self):
        (self.proc,self.pipe) = spawn_sudo(self)
        if self.proc.poll() is not None:
            raise RuntimeError("sudo helper process terminated unexpectedly")
        #  If threading is available, run a background thread to monitor
        #  the sudo process.  If it dies, terminate things immediately.
        if threading:
            self._do_monitor_proc = True
            monitor_thread = threading.Thread(target=self._monitor_proc)
            monitor_thread.daemon = True
            monitor_thread.start()
        #  Try to read initialisation message from the pipe.
        #  If this fails, the helper program must have died.
        try:
            msg = self.pipe.read()
        except EOFError:
            msg = b("")
        if msg != b("READY"):
            self.close()
            raise RuntimeError("failed to spawn helper app")
        if threading:
            self._do_monitor_proc = False
            monitor_thread.join()

    def _monitor_proc(self):
        while self._do_monitor_proc:
            if self.proc.poll() is not None:
                self.pipe._recover()
                self.pipe.close()
                break
            time.sleep(0)

    def close(self):
        self.pipe.write(b("CLOSE"))
        self.pipe.read()
        self.closed = True

    def terminate(self):
        if not self.closed:
            self.close()
        self.pipe.close()
        self.pipe = None
        self.proc.terminate()

    def run(self,pipe):
        self.target.sudo_proxy = None
        pipe.write(b("READY"))
        try:
            #  Process incoming commands in a loop.
            while True:
                try:
                    methname = pipe.read().decode("ascii")
                    if methname == "CLOSE":
                        pipe.write(b("CLOSING"))
                        break
                    else:
                        argtypes = _get_sudo_argtypes(self.target,methname)
                        iterator = _get_sudo_iterator(self.target,methname)
                        if argtypes is None:
                            msg = "attribute '%s' not allowed from sudo"
                            raise AttributeError(msg % (attr,))
                        method = getattr(self.target,methname)
                        args = []
                        for t in argtypes:
                            if t is str:
                                args.append(pipe.read().decode("ascii"))
                            else:
                                args.append(t(pipe.read()))
                        try:
                            res = method(*args)
                        except Exception, e:
                            pipe.write(pickle.dumps((False,e)))
                        else:
                            if not iterator:
                                pipe.write(pickle.dumps((True,res)))
                            else:
                                try:
                                    for item in res:
                                        pipe.write(pickle.dumps((True,item)))
                                except Exception, e:
                                    pipe.write(pickle.dumps((False,e)))
                                else:
                                    SI = StopIteration
                                    pipe.write(pickle.dumps((False,SI)))
                except EOFError:
                    break
            #  Stay alive until the pipe is closed, but don't execute
            #  any further commands.
            while True:
                try:
                    pipe.read()
                except EOFError:
                    break
        finally:
            pipe.close()

    def __getattr__(self,attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        target = self.__dict__["target"]
        if _get_sudo_argtypes(target,attr) is None:
            msg = "attribute '%s' not allowed from sudo" % (attr,)
            raise AttributeError(msg)
        method = getattr(target,attr)
        pipe = self.__dict__["pipe"]
        if not _get_sudo_iterator(target,attr):
            @functools.wraps(method.im_func)
            def wrapper(*args):
                pipe.write(method.im_func.func_name.encode("ascii"))
                for arg in args:
                    pipe.write(str(arg).encode("ascii"))
                (success,result) = pickle.loads(pipe.read())
                if not success:
                    raise result
                return result
        else:
            @functools.wraps(method.im_func)
            def wrapper(*args):
                pipe.write(method.im_func.func_name.encode("ascii"))
                for arg in args:
                    pipe.write(str(arg).encode("ascii"))
                (success,result) = pickle.loads(pipe.read())
                while success:
                    yield result
                    (success,result) = pickle.loads(pipe.read())
                if result is not StopIteration:
                    raise result
        setattr(self,attr,wrapper)
        return wrapper


def allow_from_sudo(*argtypes,**kwds):
    """Method decorator to allow access to a method via the sudo proxy.

    This decorator wraps an Esky method so that it can be called via the
    esky's sudo proxy.  It is also used to declare type conversions/checks
    on the arguments given to the method.  Example:

        @allow_from_sudo(str)
        def install_version(self,version):
            if self.sudo_proxy is not None:
                return self.sudo_proxy.install_version(version)
            ...

    Note that there are two aspects to transparently tunneling a method call
    through the sudo proxy: allowing it via this decorator, and actually 
    passing on the call to the proxy object.  I have no intention of making
    this any more hidden, because the fact that a method can have escalated
    privileges is something that that needs to be very obvious from the code.
    """
    def decorator(func):
        func._esky_sudo_argtypes = argtypes
        func._esky_sudo_iterator = kwds.pop("iterator",False)
        return func
    return decorator


def _get_sudo_argtypes(obj,methname):
    """Get the argtypes list for the given method.

    This searches the base classes of obj if the given method is not declared
    allowed_from_sudo, so that people don't have to constantly re-apply the
    decorator.
    """
    for base in _get_mro(obj):
        try:
            argtypes = base.__dict__[methname]._esky_sudo_argtypes
        except (KeyError,AttributeError):
            pass
        else:
            return argtypes
    return None

def _get_sudo_iterator(obj,methname):
    """Get the iterator flag for the given method.

    This searches the base classes of obj if the given method is not declared
    allowed_from_sudo, so that people don't have to constantly re-apply the
    decorator.
    """
    for base in _get_mro(obj):
        try:
            iterator = base.__dict__[methname]._esky_sudo_iterator
        except (KeyError,AttributeError):
            pass
        else:
            return iterator
    return False

def _get_mro(obj):
    """Get the method resolution order for an object.

    In other words, get the list of classes what are used to look up methods
    on the given object, in the order in which they'll be consulted.
    """
    try:
        return obj.__class__.__mro__
    except AttributeError:
        return _get_oldstyle_mro(obj.__class__,set())

def _get_oldstyle_mro(cls,seen):
    """Get the method resolution order bor an old-style class.

    This is essentially a bottom-up left-to-right iteration of all the
    superclasses.
    """
    yield cls
    seen.add(cls)
    for base in cls.__bases__:
        if base not in seen:
            for ancestor in _get_oldstyle_mro(base,seen):
                yield ancestor


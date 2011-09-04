#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.sudo.sudo_unix:  unix platform-specific functionality for esky.sudo

"""

import os
import sys
import errno
import struct
import signal
import subprocess
import tempfile
from base64 import b64encode, b64decode
from functools import wraps

from esky.sudo import sudo_base as base
import esky.slaveproc

pickle = base.pickle
HIGHEST_PROTOCOL = pickle.HIGHEST_PROTOCOL


def has_root():
    """Check whether the use current has root access."""
    return (os.geteuid() == 0)


def can_get_root():
    """Check whether the usee may be able to get root access.

    This is currently always True on unix-like platforms, since we have no
    sensible way of peering inside the sudoers file.
    """
    return True


class KillablePopen(subprocess.Popen):
    """Popen that's guaranteed killable, even on python2.5."""
    if not hasattr(subprocess.Popen,"terminate"):
        def terminate(self):
            import signal
            os.kill(self.pid,signal.SIGTERM)


class SecureStringPipe(base.SecureStringPipe):
    """A two-way pipe for securely communicating with a sudo subprocess.

    On unix this is implemented as a pair of fifos.  It would be more secure
    to use anonymous pipes, but they're not reliably inherited through sudo
    wrappers such as gksudo.

    Unfortunately this leaves the pipes wide open to hijacking by other
    processes running as the same user.  Security depends on secrecy of the
    message-hashing token, which we pass to the slave in its env vars.
    """

    def __init__(self,token=None,data=None):
        super(SecureStringPipe,self).__init__(token)
        self.rfd = None
        self.wfd = None
        if data is None:
            self.tdir = tempfile.mkdtemp()
            self.rnm = os.path.join(self.tdir,"master")
            self.wnm = os.path.join(self.tdir,"slave")
            os.mkfifo(self.rnm,0600)
            os.mkfifo(self.wnm,0600)
        else:
            self.tdir,self.rnm,self.wnm = data

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def connect(self):
        return SecureStringPipe(self.token,(self.tdir,self.wnm,self.rnm))

    def _read(self,size):
        return os.read(self.rfd,size)

    def _write(self,data):
        return os.write(self.wfd,data)

    def _open(self):
        if self.rnm.endswith("master"):
            self.rfd = os.open(self.rnm,os.O_RDONLY)
            self.wfd = os.open(self.wnm,os.O_WRONLY)
        else:
            self.wfd = os.open(self.wnm,os.O_WRONLY)
            self.rfd = os.open(self.rnm,os.O_RDONLY)
        os.unlink(self.wnm)

    def _recover(self):
        try:
            os.close(os.open(self.rnm,os.O_WRONLY))
        except EnvironmentError:
            pass
        try:
            os.close(os.open(self.wnm,os.O_RDONLY))
        except EnvironmentError:
            pass

    def close(self):
        if self.rfd is not None:
            os.close(self.rfd)
            os.close(self.wfd)
            self.rfd = None
            self.wfd = None
            if os.path.isfile(self.wnm):
                os.unlink(self.wnm)
            try:
                if not os.listdir(self.tdir):
                    os.rmdir(self.tdir)
            except EnvironmentError, e:
                if e.errno != errno.ENOENT:
                    raise
        super(SecureStringPipe,self).close()


def find_exe(name,*args):
    path = os.environ.get("PATH","/bin:/usr/bin").split(":")
    if getattr(sys,"frozen",False):
        path.append(os.path.dirname(sys.executable))
    for dir in path:
        exe = os.path.join(dir,name)
        if os.path.exists(exe):
            return [exe] + list(args)
    return None


def spawn_sudo(proxy):
    """Spawn the sudo slave process, returning proc and a pipe to message it."""
    rnul = open(os.devnull,"r")
    wnul = open(os.devnull,"w")
    pipe = SecureStringPipe()
    c_pipe = pipe.connect()
    if not getattr(sys,"frozen",False):
        exe = [sys.executable,"-c","import esky; esky.run_startup_hooks()"]
    elif os.path.basename(sys.executable).lower() in ("python","pythonw"):
        exe = [sys.executable,"-c","import esky; esky.run_startup_hooks()"]
    else:
        if not esky._startup_hooks_were_run:
            raise OSError(None,"unable to sudo: startup hooks not run")
        exe = [sys.executable]
    args = ["--esky-spawn-sudo"]
    args.append(b64encode(pickle.dumps(proxy,HIGHEST_PROTOCOL)))
    # Look for a variety of sudo-like programs
    sudo = None
    display_name = "%s update" % (proxy.name,)
    if "DISPLAY" in os.environ:
        sudo = find_exe("gksudo","-k","-D",display_name,"--")
        if sudo is None:
            sudo = find_exe("kdesudo")
        if sudo is None:
            sudo = find_exe("cocoasudo","--prompt='%s'" % (display_name,))
    if sudo is None:
        sudo = find_exe("sudo")
    if sudo is None:
        sudo = []
    # Make it a slave process so it dies if we die
    exe = sudo + exe + esky.slaveproc.get_slave_process_args() + args
    # Pass the pipe in environment vars, they seem to be harder to snoop.
    env = os.environ.copy()
    env["ESKY_SUDO_PIPE"] = b64encode(pickle.dumps(c_pipe,HIGHEST_PROTOCOL))
    if sys.version_info[0] > 2:
        #  Python3 doesn't like bytestrings in the env dict
        env["ESKY_SUDO_PIPE"] = env["ESKY_SUDO_PIPE"].decode("ascii")
    # Spawn the subprocess
    kwds = dict(stdin=rnul,stdout=wnul,stderr=wnul,close_fds=True,env=env)
    proc = KillablePopen(exe,**kwds)
    return (proc,pipe)


def run_startup_hooks():
    if len(sys.argv) > 1 and sys.argv[1] == "--esky-spawn-sudo":
        if sys.version_info[0] > 2:
            proxy = pickle.loads(b64decode(sys.argv[2].encode("ascii")))
            pipe = pickle.loads(b64decode(os.environ["ESKY_SUDO_PIPE"].encode("ascii")))
        else:
            proxy = pickle.loads(b64decode(sys.argv[2]))
            pipe = pickle.loads(b64decode(os.environ["ESKY_SUDO_PIPE"]))
        proxy.run(pipe)
        sys.exit(0)



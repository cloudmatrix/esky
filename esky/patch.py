"""

  esky.patch:  directory diffing and patching support for esky.

This module forms the basis of esky's differential update support.  It defines
a compact protocol to encode the differences between two directories, and
functions to calculate and apply such patches.

"""

from __future__ import with_statement

import os
import sys
import bz2
import shutil
import hashlib
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


from esky.errors import Error

class PatchError(Error):
    """Error raised when a patch fails to apply."""
    pass


#  Commands used in the directory patching protocol.  Each of these is
#  encoded as a vint in the patch stream; unless we get really out of
#  control that should mean one byte per command.
_COMMANDS = [
  "END",         # END():              stop processing at this point
  "SET_PATH",    # SET_PATH(path):     set current target path 
  "JOIN_PATH",   # JOIN_PATH(path):    join path to the current target
  "POP_PATH",    # POP_PATH(h):        pop one level off current target
  "REMOVE",      # REMOVE():           remove the current target
  "MAKEDIR",     # MAKEDIR():          make directory at current target
  "COPY_FROM",   # COPY_FROM(path):    copy file/dir at path to current target
  "VERIFY_MD5",  # VERIFY_MD5(digest): check md5 digest of current target
  "OPEN_FILE",   # OPEN_FILE():        open current target as file to patch
  "CLOSE_FILE",  # CLOSE_FILE():       finish patching the current file
  "F_COPY",      # F_COPY(n):          copy n bytes from input file
  "F_SKIP",      # F_SKIP(n):          skip n bytes from input file
  "F_INSERT",    # F_INSERT(bytes):    insert raw bytes into output file
  "F_INS_BZ2",   # F_INS_BZ2(bytes):   insert bunzipd bytes into output file
]
for i,cmd in enumerate(_COMMANDS):
    globals()[cmd] = i


def read_vint(stream):
    """Read a vint-encoded integer from the given stream."""
    b = ord(stream.read(1))
    if b < 128:
        return b
    x = e = 0
    while b >= 128:
        x += (b - 128) << e
        e += 7
        b = ord(stream.read(1))
    x += (b << e)
    return x

def write_vint(stream,x):
    """Write a vint-encoded integer to the given stream."""
    while x >= 128:
        b = x & 127
        stream.write(chr(b | 128))
        x = x >> 7
    stream.write(chr(x))

def read_command(stream):
    """Read a command from the given stream."""
    return read_vint(stream)

def write_command(stream,cmd):
    """Write a command to the given stream."""
    write_vint(stream,cmd)

def read_bytes(stream):
    """Read a bytestring from the given stream."""
    l = read_vint(stream)
    bytes = stream.read(l)
    if len(bytes) != l:
        raise PatchError("corrupted bytestring")
    return bytes

def write_bytes(stream,bytes):
    """Write a bytestring to given stream.

    Bytestrings are encoded as [length][bytes].
    """
    write_vint(stream,len(bytes))
    stream.write(bytes)

def read_path(stream):
    """Read a unicode path from the given stream."""
    return read_bytes(stream).decode("utf-8")

def write_path(stream,path):
    """Write a unicode path to the given stream.

    Paths are encoded in utf-8.
    """
    write_bytes(stream,path.encode("utf-8"))


def calculate_digest(target,hash=hashlib.md5):
    """Calculate the digest of the given path.

    If the target is a file, its digest is calculated as normal.  It
    it is a directory, it is calculated from the digests of the contents
    of the directory.
    """
    d = hash()
    if os.path.isfile(target):
        with open(target,"rb") as f:
            data = f.read(512*1024)
            while data:
                d.update(data)
                data = f.read(512*1024)
    else:
        for nm in sorted(os.listdir(target)):
            d.update(nm)
            d.update(calculate_digest(os.path.join(target,nm)))
    return d.digest()


class Patcher(object):
    """Class interpreting our patch protocol.

    Instances of this class can be used to apply a sequence of patch commands
    to a target file or directory.
    """

    def __init__(self,target,commands):
        target = os.path.abspath(target)
        self.target = target
        self.commands = commands
        if not self.target.endswith(os.sep):
            self.target = self.target + os.sep
        self.root_dir = self.target
        self.infile = None
        self.outfile = None

    def __del__(self):
        if self.infile:
            self.infile.close()
        if self.outfile:
            self.outfile.close()

    def patch(self):
        cmd = read_command(self.commands)
        while cmd != END:
            getattr(self,"_do_" + _COMMANDS[cmd])()
            cmd = read_command(self.commands)

    def _do_SET_PATH(self):
        self.target = os.path.join(self.root_dir,read_path(self.commands))
        if not self.target.startswith(self.root_dir):
            raise PatchError("traversed outside root_dir")

    def _do_JOIN_PATH(self):
        self.target = os.path.join(self.target,read_path(self.commands))
        if not self.target.startswith(self.root_dir):
            raise PatchError("traversed outside root_dir")

    def _do_POP_PATH(self):
        self.target = os.path.dirname(self.target)
        if not self.target.endswith(os.sep):
            self.target += os.sep
        if not self.target.startswith(self.root_dir):
            raise PatchError("traversed outside root_dir")

    def _do_MAKEDIR(self):
        if os.path.exists(self.target) and not os.path.isdir(self.target):
            os.unlink(self.target)
        os.makedirs(self.target)

    def _do_REMOVE(self):
        if os.path.isdir(self.target):
            shutil.rmtree(self.target)
        elif os.path.exists(self.target):
            os.unlink(self.target)

    def _do_COPY_FROM(self):
        source_path = os.path.join(self.root_path,read_path(self.commands))
        if not source_path.startswith(self.root_dir):
            raise PatchError("traversed outside root_dir")
        if os.path.exists(self.target):
            if os.path.isdir(self.target):
                shutil.rmtree(self.target)
            else:
                os.unlink(self.target)
        if os.path.isfile(source_path):
            shutil.copy2(source_path,self.target)
        else:
            shutil.copytree(source_path,self.target)

    def _do_VERIFY_MD5(self):
        digest1 = read_bytes(self.commands)
        digest2 = calculate_digest(self.target,hashlib.md5)
        if digest1 != digest2:
            raise PatchError("incorrect MD5 digest")

    def _do_OPEN_FILE(self):
        if os.path.exists(self.target) and not os.path.isfile(self.target):
            shutil.rmtree(self.target)
        self.new_target = self.target + ".new"
        while os.path.exists(self.new_target):
            self.new_target += ".new"
        if os.path.exists(self.target):
            self.infile = open(self.target,"rb")
        else:
            self.infile = StringIO("")
        self.outfile = open(self.new_target,"wb")

    def _do_CLOSE_FILE(self):
        self.infile.close()
        self.infile = None
        self.outfile.close()
        self.outfile = None
        if os.path.exists(self.target):
           os.unlink(self.target)
        os.rename(self.new_target,self.target)

    def _do_F_COPY(self):
        n = read_vint(self.commands)
        self.outfile.write(self.infile.read(n))

    def _do_F_SKIP(self):
        n = read_vint(self.commands)
        self.infile.read(n)

    def _do_F_INSERT(self):
        data = read_bytes(self.commands)
        self.outfile.write(data)

    def _do_F_INS_BZ2(self):
        data = read_bytes(self.commands)
        self.outfile.write(bz2.decompress(data))


def write_patch(stream,source,target):
    _write_patch(stream,source,target)
    write_command(stream,SET_PATH)
    write_bytes(stream,"")
    write_command(stream,VERIFY_MD5)
    write_bytes(stream,calculate_digest(target,hashlib.md5))
    write_command(stream,END)


def _write_patch(stream,source,target):
    if os.path.isfile(target):
        #  target is a file
        if os.path.isfile(source):
            if calculate_digest(target) == calculate_digest(source):
                return
        write_command(stream,OPEN_FILE)
        with open(target,"rb") as f:
            data = f.read()
        bz2_data = bz2.compress(data)
        if len(bz2_data) < len(data):
            write_command(stream,F_INS_BZ2)
            write_bytes(stream,bz2.compress(data))
        else:
            write_command(stream,F_INSERT)
            write_bytes(stream,data)
        write_command(stream,CLOSE_FILE)
    else:
        #  target is a directory
        if not os.path.isdir(source):
            write_command(stream,MAKEDIR)
        else:
            for nm in os.listdir(source):
                if not os.path.exists(os.path.join(target,nm)):
                    write_command(stream,JOIN_PATH)
                    write_path(stream,nm)
                    write_command(stream,REMOVE)
                    write_command(stream,POP_PATH)
        for nm in os.listdir(target):
            write_command(stream,JOIN_PATH)
            write_path(stream,nm)
            _write_patch(stream,os.path.join(source,nm),os.path.join(target,nm))
            write_command(stream,POP_PATH)

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "diff":
        source = sys.argv[2]
        target = sys.argv[3]
        try:
            stream = open(sys.argv[4],"wb")
        except IndexError:
            stream = sys.stdout
        write_patch(stream,source,target)
    elif cmd == "patch":
        target = sys.argv[2]
        try:
            stream = open(sys.argv[3],"rb")
        except IndexError:
            stream = sys.stdin
        Patcher(target,stream).patch()
    else:
        raise ValueError("invalid command: " + cmd)


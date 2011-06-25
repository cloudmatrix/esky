#  Copyright (c) 2009-2010, Cloud Matrix Pty. Ltd.
#  All rights reserved; available under the terms of the BSD License.
"""

  esky.patch:  directory diffing and patching support for esky.

This module forms the basis of esky's differential update support.  It defines
a compact protocol to encode the differences between two directories, and
functions to calculate and apply patches based on this protocol.  It exposes
the following functions:

  write_patch(srcpath,tgtpath,stream):

      calculate the differences between directories (or files) "srcpath"
      and "tgtpath", and write a patch to transform the format into the
      latter to the file-like object "stream".

  apply_patch(tgtpath,stream):

      read a patch from the file-like object "stream" and apply it to the
      directory (or file) at "tgtpath".  For directories, the patch is
      applied *in-situ*.  If you want to guard against patches that fail to
      apply, patch a copy then copy it back over the original.


This module can also be executed as a script (e.g. "python -m esky.patch ...")
to calculate or apply patches from the command-line:

  python -m esky.patch diff <source> <target> <patch>

      generate a patch to transform <source> into <target>, and write it into
      file <patch> (or stdout if not specified).

  python -m esky.patch patch <source> <patch>

      transform <source> by applying the patches in the file <patch> (or
      stdin if not specified.  The modifications are made in-place.

To patch or diff zipfiles as though they were a directory, pass the "-z" or
"--zipped" option on the command-line, e.g:

  python -m esky.patch --zipped diff <source>.zip <target>.zip <patch>

To "deep unzip" the zipfiles so that any leading directories are ignored, use
the "-Z" or "--deep-zipped" option instead:

  python -m esky.patch -Z diff <source>.zip <target>.zip <patch>

This can be useful for generating differential esky updates by hand, when you
already have the corresponding zip files.

"""

from __future__ import with_statement
try:
    bytes = bytes
except NameError:
    bytes = str


import os
import sys
import bz2
import time
import shutil
import hashlib
import optparse
import zipfile
import tempfile
if sys.version_info[0] < 3:
    try:
        from cStringIO import StringIO as BytesIO
    except ImportError:
       from StringIO import StringIO as BytesIO
else:
    from io import BytesIO


#  Try to get code for working with bsdiff4-format patches.
#
#  We have three options:
#     * use the cleaned-up bsdiff4 module by Ilan Schnell.
#     * use the original cx-bsdiff module by Anthony Tuininga.
#     * use a pure-python patch-only version.
#
#  We define each one if we can, so it's available for testing purposes.
#  We then set the main "bsdiff4" name equal to the best option.
#
#  TODO: move this into a support module, it clutters up reading
#        of the code in this file
#

try:
    import bsdiff4 as bsdiff4_native
except ImportError:
    bsdiff4_native = None


try:
    import bsdiff as _cx_bsdiff
except ImportError:
    bsdiff4_cx = None
else:
    #  This wrapper code basically takes care of the bsdiff patch format,
    #  translating to/from the raw control information for the algorithm.
    class bsdiff4_cx(object):
        @staticmethod
        def diff(source,target):
            (tcontrol,bdiff,bextra) = _cx_bsdiff.Diff(source,target)
            #  Write control tuples as series of offts
            bcontrol = BytesIO()
            for c in tcontrol:
                for x in c:
                    bcontrol.write(_encode_offt(x))
            del tcontrol
            bcontrol = bcontrol.getvalue()
            #  Compress each block
            bcontrol = bz2.compress(bcontrol)
            bdiff = bz2.compress(bdiff)
            bextra = bz2.compress(bextra)
            #  Final structure is:
            #  (header)(len bcontrol)(len bdiff)(len target)(bcontrol)\
            #  (bdiff)(bextra)
            return "".join((
                "BSDIFF40",
                _encode_offt(len(bcontrol)),
                _encode_offt(len(bdiff)),
                _encode_offt(len(target)),
                bcontrol,
                bdiff,
                bextra,
            ))
        @staticmethod
        def patch(source,patch):
            #  Read the length headers
            l_bcontrol = _decode_offt(patch[8:16])
            l_bdiff = _decode_offt(patch[16:24])
            l_target = _decode_offt(patch[24:32])
            #  Read the three data blocks
            e_bcontrol = 32 + l_bcontrol
            e_bdiff = e_bcontrol + l_bdiff
            bcontrol = bz2.decompress(patch[32:e_bcontrol])
            bdiff = bz2.decompress(patch[e_bcontrol:e_bdiff])
            bextra = bz2.decompress(patch[e_bdiff:])
            #  Decode the control tuples 
            tcontrol = []
            for i in xrange(0,len(bcontrol),24):
                tcontrol.append((
                    _decode_offt(bcontrol[i:i+8]),
                    _decode_offt(bcontrol[i+8:i+16]),
                    _decode_offt(bcontrol[i+16:i+24]),
                ))
            #  Actually do the patching.
            return _cx_bsdiff.Patch(source,l_target,tcontrol,bdiff,bextra)


class bsdiff4_py(object):
    """Pure-python version of bsdiff4 module that can only patch, not diff.

    By providing a pure-python fallback, we don't force frozen apps to 
    bundle the bsdiff module in order to make use of patches.  Besides,
    the patch-applying algorithm is very simple.
    """
    #  Expose a diff method if we have one from another module, to
    #  make it easier to test this class.
    if bsdiff4_native is not None:
        @staticmethod
        def diff(source,target):
            return bsdiff4_native.diff(source,target)
    elif bsdiff4_cx is not None:
        @staticmethod
        def diff(source,target):
            return bsdiff4_cx.diff(source,target)
    else:
        diff = None
    @staticmethod
    def patch(source,patch):
        #  Read the length headers
        l_bcontrol = _decode_offt(patch[8:16])
        l_bdiff = _decode_offt(patch[16:24])
        l_target = _decode_offt(patch[24:32])
        #  Read the three data blocks
        e_bcontrol = 32 + l_bcontrol
        e_bdiff = e_bcontrol + l_bdiff
        bcontrol = bz2.decompress(patch[32:e_bcontrol])
        bdiff = bz2.decompress(patch[e_bcontrol:e_bdiff])
        bextra = bz2.decompress(patch[e_bdiff:])
        #  Decode the control tuples 
        tcontrol = []
        for i in xrange(0,len(bcontrol),24):
            tcontrol.append((
                _decode_offt(bcontrol[i:i+8]),
                _decode_offt(bcontrol[i+8:i+16]),
                _decode_offt(bcontrol[i+16:i+24]),
            ))
        #  Actually do the patching.
        #  This is the bdiff4 patch algorithm in slow, pure python.
        source = BytesIO(source)
        result = BytesIO()
        bdiff = BytesIO(bdiff)
        bextra = BytesIO(bextra)
        for (x,y,z) in tcontrol:
            diff_data = bdiff.read(x)
            orig_data = source.read(x)
            if sys.version_info[0] < 3:
                for i in xrange(len(diff_data)):
                    result.write(chr((ord(diff_data[i])+ord(orig_data[i]))%256))
            else:
                for i in xrange(len(diff_data)):
                    result.write(bytes([(diff_data[i]+orig_data[i])%256]))
            result.write(bextra.read(y))
            source.seek(z,os.SEEK_CUR)
        return result.getvalue()


if bsdiff4_native is not None:
    bsdiff4 = bsdiff4_native
elif bsdiff4_cx is not None:
    bsdiff4 = bsdiff4_cx
else:
    bsdiff4 = bsdiff4_py


#  Default size of blocks to use when diffing a file.  4M seems reasonable.
#  Setting this higher generates smaller patches at the cost of higher
#  memory use (and bsdiff is a memory hog at the best of times...)
DIFF_WINDOW_SIZE = 1024 * 1024 * 4

#  Highest patch version that can be processed by this module.
HIGHEST_VERSION = 1

#  Header bytes included in the patch file
PATCH_HEADER = "ESKYPTCH".encode("ascii")


from esky.errors import Error
from esky.util import extract_zipfile, create_zipfile, deep_extract_zipfile,\
                      zipfile_common_prefix_dir, really_rmtree, really_rename

__all__ = ["PatchError","DiffError","main","write_patch","apply_patch",
           "Differ","Patcher"]



class PatchError(Error):
    """Error raised when a patch fails to apply."""
    pass

class DiffError(Error):
    """Error raised when a diff can't be generated."""
    pass


#  Commands used in the directory patching protocol.  Each of these is
#  encoded as a vint in the patch stream; unless we get really out of
#  control and have more than 127 commands, this means one byte per command.
#
#  It's very important that you don't reorder these commands.  Their order
#  in this list determines what byte each command is assigned, so doing
#  anything but adding to the end will break all existing patches!
#
_COMMANDS = [
 "END",           # END():               stop processing current context
 "SET_PATH",      # SET_PATH(path):      set current target path 
 "JOIN_PATH",     # JOIN_PATH(path):     join path to the current target
 "POP_PATH",      # POP_PATH(h):         pop one level off current target
 "POP_JOIN_PATH", # POP_JOIN_PATH(path): pop the current path, then join
 "VERIFY_MD5",    # VERIFY_MD5(dgst):    check md5 digest of current target
 "REMOVE",        # REMOVE():            remove the current target
 "MAKEDIR",       # MAKEDIR():           make directory at current target
 "COPY_FROM",     # COPY_FROM(path):     copy item at path to current target
 "MOVE_FROM",     # MOVE_FROM(path):     move item at path to current target
 "PF_COPY",       # PF_COPY(n):          patch file; copy n bytes from input
 "PF_SKIP",       # PF_SKIP(n):          patch file; skip n bytes from input
 "PF_INS_RAW",    # PF_INS_RAW(bytes):   patch file; insert raw bytes 
 "PF_INS_BZ2",    # PF_INS_BZ2(bytes):   patch file; insert unbzip'd bytes
 "PF_BSDIFF4",    # PF_BSDIFF4(n,p):     patch file; bsdiff4 from n input bytes
 "PF_REC_ZIP",    # PF_REC_ZIP(m,cs):    patch file; recurse into zipfile
 "CHMOD",         # CHMOD(mode):         set mode of current target
]

# Make commands available as global variables
for i,cmd in enumerate(_COMMANDS):
    globals()[cmd] = i


def apply_patch(target,stream,**kwds):
    """Apply patch commands from the given stream to the given target.

    'target' must be the path of a file or directory, and 'stream' an object
    supporting the read() method.  Patch protocol commands will be read from
    the stream and applied in sequence to the target.
    """
    Patcher(target,stream,**kwds).patch()


def write_patch(source,target,stream,**kwds):
    """Generate patch commands to transform source into target.

    'source' and 'target' must be paths to a file or directory, and 'stream'
    an object supporting the write() method.  Patch protocol commands to
    transform 'source' into 'target' will be generated and written sequentially
    to the stream.
    """
    Differ(stream,**kwds).diff(source,target)


def _read_vint(stream):
    """Read a vint-encoded integer from the given stream."""
    b = stream.read(1)
    if not b:
        raise EOFError
    b = ord(b)
    if b < 128:
        return b
    x = e = 0
    while b >= 128:
        x += (b - 128) << e
        e += 7
        b = stream.read(1)
        if not b:
            raise EOFError
        b = ord(b)
    x += (b << e)
    return x

if sys.version_info[0] > 2:
    def _write_vint(stream,x):
        """Write a vint-encoded integer to the given stream."""
        while x >= 128:
            b = x & 127
            stream.write(bytes([b | 128]))
            x = x >> 7
        stream.write(bytes([x]))
else:
    def _write_vint(stream,x):
        """Write a vint-encoded integer to the given stream."""
        while x >= 128:
            b = x & 127
            stream.write(chr(b | 128))
            x = x >> 7
        stream.write(chr(x))


def _read_zipfile_metadata(stream):
    """Read zipfile metadata from the given stream.

    The result is a zipfile.ZipFile object where all members are zero length.
    """
    return zipfile.ZipFile(stream,"r")


def _write_zipfile_metadata(stream,zfin):
    """Write zipfile metadata to the given stream.

    For simplicity, the metadata is represented as a zipfile with the same
    members as the given zipfile, but where they all have zero length.
    """
    zfout = zipfile.ZipFile(stream,"w")
    try:
        for zinfo in zfin.infolist():
            zfout.writestr(zinfo,"")
    finally:
        zfout.close()


def paths_differ(path1,path2):
    """Check whether two paths differ."""
    if os.path.isdir(path1):
        if not os.path.isdir(path2):
            return True
        for nm in os.listdir(path1):
            if paths_differ(os.path.join(path1,nm),os.path.join(path2,nm)):
                return True
        for nm in os.listdir(path2):
            if not os.path.exists(os.path.join(path1,nm)):
                return True
    elif os.path.isfile(path1):
        if not os.path.isfile(path2):
            return True
        if os.stat(path1).st_size != os.stat(path2).st_size:
            return True
        with open(path1,"rb") as f1:
            with open(path2,"rb") as f2:
                data1 = f1.read(1024*16)
                data2 = f2.read(1024*16)
                while data1:
                    if data1 != data2:
                        return True
                    data1 = f1.read(1024*16)
                    data2 = f2.read(1024*16)
                if data1 != data2:
                    return True
    elif os.path.exists(path2):
        return True
    return False

    

def calculate_digest(target,hash=hashlib.md5):
    """Calculate the digest of the given path.

    If the target is a file, its digest is calculated as normal.  If it is
    a directory, it is calculated from the names and digests of its contents.
    """
    d = hash()
    if os.path.isdir(target):
        for nm in sorted(os.listdir(target)):
            d.update(nm.encode("utf8"))
            d.update(calculate_digest(os.path.join(target,nm)))
    else:
        with open(target,"rb") as f:
            data = f.read(1024*16)
            while data:
                d.update(data)
                data = f.read(1024*16)
    return d.digest()


class Patcher(object):
    """Class interpreting our patch protocol.

    Instances of this class can be used to apply a sequence of patch commands
    to a target file or directory.  You can think of it as a little automaton
    that edits a directory in-situ.
    """

    def __init__(self,target,commands,dry_run=False):
        target = os.path.abspath(target)
        self.target = target
        self.new_target = None
        self.commands = commands
        self.root_dir = self.target
        self.infile = None
        self.outfile = None
        self.dry_run = dry_run
        self._workdir = tempfile.mkdtemp()
        self._context_stack = []

    def __del__(self):
        if self.infile:
            self.infile.close()
        if self.outfile:
            self.outfile.close()
        if self._workdir and shutil:
            really_rmtree(self._workdir)

    def _read(self,size):
        """Read the given number of bytes from the command stream."""
        return self.commands.read(size)

    def _read_int(self):
        """Read an integer from the command stream."""
        i = _read_vint(self.commands)
        if self.dry_run:
            print "  ", i
        return i

    def _read_command(self):
        """Read the next command to be processed."""
        cmd = _read_vint(self.commands)
        if self.dry_run:
            print _COMMANDS[cmd]
        return cmd

    def _read_bytes(self):
        """Read a bytestring from the command stream."""
        l = _read_vint(self.commands)
        bytes = self.commands.read(l)
        if len(bytes) != l:
            raise PatchError("corrupted bytestring")
        if self.dry_run:
            print "   [%s bytes]" % (len(bytes),)
        return bytes

    def _read_path(self):
        """Read a unicode path from the given stream."""
        l = _read_vint(self.commands)
        bytes = self.commands.read(l)
        if len(bytes) != l:
            raise PatchError("corrupted path")
        path = bytes.decode("utf-8")
        if self.dry_run:
            print "  ", path
        return path

    def _check_begin_patch(self):
        """Begin patching the current file, if not already.

        This method is called by all file-patching commands; if there is
        no file open for patching then the current target is opened.
        """
        if not self.outfile and not self.dry_run:
            if os.path.exists(self.target) and not os.path.isfile(self.target):
                really_rmtree(self.target)
            self.new_target = self.target + ".new"
            while os.path.exists(self.new_target):
                self.new_target += ".new"
            if os.path.exists(self.target):
                self.infile = open(self.target,"rb")
            else:
                self.infile = BytesIO("".encode("ascii"))
            self.outfile = open(self.new_target,"wb")
            if os.path.isfile(self.target):
                mod = os.stat(self.target).st_mode
                os.chmod(self.new_target,mod)

    def _check_end_patch(self):
        """Finish patching the current file, if there is one.

        This method is called by all non-file-patching commands; if there is
        a file open for patching then it is closed and committed.
        """
        if self.outfile and not self.dry_run:
            self.infile.close()
            self.infile = None
            self.outfile.close()
            self.outfile = None
            if os.path.exists(self.target):
                os.unlink(self.target)
                if sys.platform == "win32":
                    time.sleep(0.01)
            really_rename(self.new_target,self.target)
            self.new_target = None

    def _check_path(self,path=None):
        """Check that we're not traversing outside the root."""
        if path is None:
            path = self.target
        if path != self.root_dir:
            if not path.startswith(self.root_dir + os.sep):
                raise PatchError("traversed outside root_dir")

    def _blank_state(self):
        """Save current state, then blank it out.

        The previous state is returned.
        """
        state = self._save_state()
        self.infile = None
        self.outfile = None
        self.new_target = None
        return state
        
    def _save_state(self):
        """Return the current state, for later restoration."""
        return (self.target,self.root_dir,self.infile,self.outfile,self.new_target)

    def _restore_state(self,state):
        """Restore the object to a previously-saved state."""
        (self.target,self.root_dir,self.infile,self.outfile,self.new_target) = state

    def patch(self):
        """Interpret and apply patch commands to the target.

        This is a simple command loop that dispatches to the _do_<CMD>
        methods defined below.  It keeps processing until one of them
        raises EOFError.
        """
        header = self._read(len(PATCH_HEADER))
        if header != PATCH_HEADER:
            raise PatchError("not an esky patch file [%s]" % (header,))
        version = self._read_int()
        if version > HIGHEST_VERSION:
            raise PatchError("esky patch version %d not supported"%(version,))
        try:
            while True:
                cmd = self._read_command()
                getattr(self,"_do_" + _COMMANDS[cmd])()
        except EOFError:
            self._check_end_patch()
        finally:
            if self.infile:
                self.infile.close()
                self.infile = None
            if self.outfile:
                self.outfile.close()
                self.outfile = None

    def _do_END(self):
        """Execute the END command.

        If there are entries on the context stack, this pops and executes
        the topmost entry.  Otherwise, it exits the main command loop.
        """
        self._check_end_patch()
        if self._context_stack:
            self._context_stack.pop()()
        else:
            raise EOFError

    def _do_SET_PATH(self):
        """Execute the SET_PATH command.

        This reads a path from the command stream, and sets the current
        target path to that path.
        """
        self._check_end_patch()
        path = self._read_path()
        if path:
            self.target = os.path.join(self.root_dir,path)
        else:
            self.target = self.root_dir
        self._check_path()

    def _do_JOIN_PATH(self):
        """Execute the JOIN_PATH command.

        This reads a path from the command stream, and joins it to the
        current target path.
        """
        self._check_end_patch()
        path = self._read_path()
        self.target = os.path.join(self.target,path)
        self._check_path()

    def _do_POP_PATH(self):
        """Execute the POP_PATH command.

        This pops one name component from the current target path.  It
        is an error to attempt to pop past the root directory.
        """
        self._check_end_patch()
        while self.target.endswith(os.sep):
            self.target = self.target[:-1]
        self.target = os.path.dirname(self.target)
        self._check_path()

    def _do_POP_JOIN_PATH(self):
        """Execute the POP_JOIN_PATH command.

        This pops one name component from the current target path, then
        joins the path read from the command stream.
        """
        self._do_POP_PATH()
        self._do_JOIN_PATH()

    def _do_VERIFY_MD5(self):
        """Execute the VERIFY_MD5 command.

        This reads 16 bytes from the command stream, and compares them to
        the calculated digest for the current target path.  If they differ,
        a PatchError is raised.
        """
        self._check_end_patch()
        digest = self._read(16)
        assert len(digest) == 16
        if not self.dry_run:
            if digest != calculate_digest(self.target,hashlib.md5):
                raise PatchError("incorrect MD5 digest for %s" % (self.target,))

    def _do_MAKEDIR(self):
        """Execute the MAKEDIR command.

        This makes a directory at the current target path.  It automatically
        removes any existing entry at that path, as well as creating any
        intermediate directories.
        """
        self._check_end_patch()
        if not self.dry_run:
            if os.path.isdir(self.target):
                really_rmtree(self.target)
            elif os.path.exists(self.target):
                os.unlink(self.target)
            os.makedirs(self.target)

    def _do_REMOVE(self):
        """Execute the REMOVE command.

        This forcibly removes the file or directory at the current target path.
        """
        self._check_end_patch()
        if not self.dry_run:
            if os.path.isdir(self.target):
                really_rmtree(self.target)
            elif os.path.exists(self.target):
                os.unlink(self.target)

    def _do_COPY_FROM(self):
        """Execute the COPY_FROM command.

        This reads a path from the command stream, and copies whatever is
        at that path to the current target path.  The source path is
        interpreted relative to the directory containing the current path;
        this caters for the common case of copying a file within the same
        directory.
        """
        self._check_end_patch()
        source_path = os.path.join(os.path.dirname(self.target),self._read_path())
        self._check_path(source_path)
        if not self.dry_run:
            if os.path.exists(self.target):
                if os.path.isdir(self.target):
                    really_rmtree(self.target)
                else:
                    os.unlink(self.target)
            if os.path.isfile(source_path):
                shutil.copy2(source_path,self.target)
            else:
                shutil.copytree(source_path,self.target)

    def _do_MOVE_FROM(self):
        """Execute the MOVE_FROM command.

        This reads a path from the command stream, and moves whatever is
        at that path to the current target path.  The source path is
        interpreted relative to the directory containing the current path;
        this caters for the common case of moving a file within the same
        directory.
        """
        self._check_end_patch()
        source_path = os.path.join(os.path.dirname(self.target),self._read_path())
        self._check_path(source_path)
        if not self.dry_run:
            if os.path.exists(self.target):
                if os.path.isdir(self.target):
                    really_rmtree(self.target)
                else:
                    os.unlink(self.target)
                if sys.platform == "win32":
                    time.sleep(0.01)
            really_rename(source_path,self.target)

    def _do_PF_COPY(self):
        """Execute the PF_COPY command.

        This generates new data for the file currently being patched.  It
        reads an integer from the command stream, then copies that many bytes
        directory from the source file into the target file.
        """
        self._check_begin_patch()
        n = self._read_int()
        if not self.dry_run:
            self.outfile.write(self.infile.read(n))

    def _do_PF_SKIP(self):
        """Execute the PF_SKIP command.

        This reads an integer from the command stream, then moves the source
        file pointer by that amount without changing the target file.
        """
        self._check_begin_patch()
        n = self._read_int()
        if not self.dry_run:
            self.infile.read(n)

    def _do_PF_INS_RAW(self):
        """Execute the PF_INS_RAW command.

        This generates new data for the file currently being patched.  It
        reads a bytestring from the command stream and writes it directly
        into the target file.
        """
        self._check_begin_patch()
        data = self._read_bytes()
        if not self.dry_run:
            self.outfile.write(data)

    def _do_PF_INS_BZ2(self):
        """Execute the PF_INS_BZ2 command.

        This generates new data for the file currently being patched.  It
        reads a bytestring from the command stream, decompresses it using
        bz2 and and write the result into the target file.
        """
        self._check_begin_patch()
        data = bz2.decompress(self._read_bytes())
        if not self.dry_run:
            self.outfile.write(data)

    def _do_PF_BSDIFF4(self):
        """Execute the PF_BSDIFF4 command.

        This reads an integer N and a BSDIFF4-format patch bytestring from
        the command stream.  It then reads N bytes from the source file,
        applies the patch to these bytes, and writes the result into the
        target file.
        """
        self._check_begin_patch()
        n = self._read_int()
        # Restore the standard bsdiff header bytes
        patch = "BSDIFF40".encode("ascii") + self._read_bytes()
        if not self.dry_run:
            source = self.infile.read(n)
            if len(source) != n:
                raise PatchError("insufficient source data in %s" % (self.target,))
            self.outfile.write(bsdiff4.patch(source,patch))

    def _do_PF_REC_ZIP(self):
        """Execute the PF_REC_ZIP command.

        This patches the current target by treating it as a zipfile and
        recursing into it.  It extracts the source file to a temp directory,
        then reads commands and applies them to that directory.

        This command expects two END-terminated blocks of sub-commands.  The
        first block patches the zipfile metadata, and the second patches the
        actual contents of the zipfile.
        """
        self._check_begin_patch()
        if not self.dry_run:
            workdir = os.path.join(self._workdir,str(len(self._context_stack)))
            os.mkdir(workdir)
            t_temp = os.path.join(workdir,"contents")
            m_temp = os.path.join(workdir,"meta")
            z_temp = os.path.join(workdir,"result.zip")
        cur_state = self._blank_state()
        zfmeta = [None]  # stupid lack of mutable closure variables...
        #  First we process a set of commands to generate the zipfile metadata.
        def end_metadata():
            if not self.dry_run:
                zfmeta[0] = _read_zipfile_metadata(m_temp)
                self.target = t_temp
        #  Then we process a set of commands to patch the actual contents.
        def end_contents():
            self._restore_state(cur_state)
            if not self.dry_run:
                create_zipfile(t_temp,z_temp,members=zfmeta[0].infolist())
                with open(z_temp,"rb") as f:
                    data = f.read(1024*16)
                    while data:
                        self.outfile.write(data)
                        data = f.read(1024*16)
                zfmeta[0].close()
                really_rmtree(workdir)
        self._context_stack.append(end_contents)
        self._context_stack.append(end_metadata)
        if not self.dry_run:
            #  Begin by writing the current zipfile metadata to a temp file.
            #  This will be patched, then end_metadata() will be called.
            with open(m_temp,"wb") as f:
                zf = zipfile.ZipFile(self.target)
                try:
                    _write_zipfile_metadata(f,zf)
                finally:
                    zf.close()
            extract_zipfile(self.target,t_temp)
            self.root_dir = workdir
            self.target = m_temp

    def _do_CHMOD(self):
        """Execute the CHMOD command.

        This reads an integer from the command stream, and sets the mode
        of the current target to that integer.
        """
        self._check_end_patch()
        mod = self._read_int()
        if not self.dry_run:
            os.chmod(self.target,mod)


class Differ(object):
    """Class generating our patch protocol.

    Instances of this class can be used to generate a sequence of patch
    commands to transform one file/directory into another.
    """

    def __init__(self,outfile,diff_window_size=None):
        if not diff_window_size:
            diff_window_size = DIFF_WINDOW_SIZE
        self.diff_window_size = diff_window_size
        self.outfile = outfile
        self._pending_pop_path = False

    def _write(self,data):
        self.outfile.write(data)

    def _write_int(self,i):
        _write_vint(self.outfile,i)

    def _write_command(self,cmd):
        """Write the given command to the stream.

        This does some simple optimisations to collapse sequences of commands
        into a single command - current only around path manipulation.
        """
        if cmd == POP_PATH:
            if self._pending_pop_path:
                _write_vint(self.outfile,POP_PATH)
            else:
                self._pending_pop_path = True
        elif self._pending_pop_path:
            self._pending_pop_path = False
            if cmd == JOIN_PATH:
                _write_vint(self.outfile,POP_JOIN_PATH)
            elif cmd == SET_PATH:
                _write_vint(self.outfile,SET_PATH)
            else:
                _write_vint(self.outfile,POP_PATH)
                _write_vint(self.outfile,cmd)
        else:
            _write_vint(self.outfile,cmd)

    def _write_bytes(self,bytes):
        _write_vint(self.outfile,len(bytes))
        self._write(bytes)

    def _write_path(self,path):
        self._write_bytes(path.encode("utf8"))

    def diff(self,source,target):
        """Generate patch commands to transform source into target.

        'source' and 'target' must be paths to a file or directory.  Patch
        protocol commands to transform 'source' into 'target' will be generated
        and written sequentially to the output file.
        """
        source = os.path.abspath(source)
        target = os.path.abspath(target)
        self._write(PATCH_HEADER)
        self._write_int(HIGHEST_VERSION)
        self._diff(source,target)
        self._write_command(SET_PATH)
        self._write_bytes("".encode("ascii"))
        self._write_command(VERIFY_MD5)
        self._write(calculate_digest(target,hashlib.md5))

    def _diff(self,source,target):
        """Recursively generate patch commands to transform source into target.

        This is the workhorse for the diff() method - it recursively
        generates the patch commands for a given (source,target) pair.  The
        main diff() method adds some header and footer commands.
        """
        if os.path.isdir(target):
            self._diff_dir(source,target)
        elif os.path.isfile(target):
            self._diff_file(source,target)
        else:
            #  We can't deal with any other objects for the moment.
            #  Could eventually add support for e.g. symlinks.
            raise DiffError("unknown filesystem object: " + target)

    def _diff_dir(self,source,target):
        """Generate patch commands for when the target is a directory."""
        if not os.path.isdir(source):
            self._write_command(MAKEDIR)
        moved_sources = []
        for nm in os.listdir(target):
            s_nm = os.path.join(source,nm)
            t_nm = os.path.join(target,nm)
            #  If this is a new file or directory, try to find a promising
            #  sibling against which to diff.  This might generate a few
            #  spurious COPY_FROM and REMOVE commands, but in return we
            #  get a better chance of diffing against something.
            at_path = False
            if not os.path.exists(s_nm):
                sibnm = self._find_similar_sibling(source,target,nm)
                if sibnm is not None:
                    s_nm = os.path.join(source,sibnm)
                    at_path = True
                    self._write_command(JOIN_PATH)
                    self._write_path(nm)
                    if os.path.exists(os.path.join(target,sibnm)):
                        self._write_command(COPY_FROM)
                    else:
                        self._write_command(MOVE_FROM)
                        moved_sources.append(sibnm)
                    self._write_path(sibnm)
            #  Recursively diff against the selected source directory
            if paths_differ(s_nm,t_nm):
                if not at_path:
                    self._write_command(JOIN_PATH)
                    self._write_path(nm)
                    at_path = True
                self._diff(s_nm,t_nm)
            #  Clean up .pyc files, as they can be generated automatically
            #  and cause digest verification to fail.
            if nm.endswith(".py"):
                if not os.path.exists(t_nm+"c"):
                    if at_path:
                        self._write_command(POP_JOIN_PATH)
                    else:
                        self._write_command(JOIN_PATH)
                    self._write_path(nm+"c")
                    at_path = True
                    self._write_command(REMOVE)
                if not os.path.exists(t_nm+"o"):
                    if at_path:
                        self._write_command(POP_JOIN_PATH)
                    else:
                        self._write_command(JOIN_PATH)
                    self._write_path(nm+"o")
                    at_path = True
                    self._write_command(REMOVE)
            if at_path:
                self._write_command(POP_PATH)
        #  Remove anything that's no longer in the target dir
        if os.path.isdir(source):
            for nm in os.listdir(source):
                if not os.path.exists(os.path.join(target,nm)):
                    if not nm in moved_sources:
                        self._write_command(JOIN_PATH)
                        self._write_path(nm)
                        self._write_command(REMOVE)
                        self._write_command(POP_PATH)
        #  Adjust mode if necessary
        t_mod = os.stat(target).st_mode
        if os.path.isdir(source):
            s_mod = os.stat(source).st_mode
            if s_mod != t_mod:
                self._write_command(CHMOD)
                self._write_int(t_mod)
        else:
            self._write_command(CHMOD)
            self._write_int(t_mod)

    def _diff_file(self,source,target):
        """Generate patch commands for when the target is a file."""
        if paths_differ(source,target):
            if not os.path.isfile(source):
                self._diff_binary_file(source,target)
            elif target.endswith(".zip") and source.endswith(".zip"):
                self._diff_dotzip_file(source,target)
            else:
                self._diff_binary_file(source,target)
        #  Adjust mode if necessary
        t_mod = os.stat(target).st_mode
        if os.path.isfile(source):
            s_mod = os.stat(source).st_mode
            if s_mod != t_mod:
                self._write_command(CHMOD)
                self._write_int(t_mod)
        else:
            self._write_command(CHMOD)
            self._write_int(t_mod)

    def _open_and_check_zipfile(self,path):
        """Open the given path as a zipfile, and check its suitability.

        Returns either the ZipFile object, or None if we can't diff it
        as a zipfile.
        """
        try:
            zf = zipfile.ZipFile(path,"r")
        except (zipfile.BadZipfile,zipfile.LargeZipFile):
            return None
        else:
            # Diffing empty zipfiles is kinda pointless
            if not zf.filelist:
                zf.close()
                return None
            # Can't currently handle zipfiles with comments
            if zf.comment:
                zf.close()
                return None
            # Can't currently handle zipfiles with prepended data
            if zf.filelist[0].header_offset != 0:
                zf.close()
                return None
            # Hooray! Looks like something we can use.
            return zf
      
    def _diff_dotzip_file(self,source,target):
        s_zf = self._open_and_check_zipfile(source)
        if s_zf is None:
            self._diff_binary_file(source,target)
        else:
            t_zf = self._open_and_check_zipfile(target)
            if t_zf is None:
                s_zf.close()
                self._diff_binary_file(source,target)
            else:
                try:
                    self._write_command(PF_REC_ZIP)
                    with _tempdir() as workdir:
                        #  Write commands to transform source metadata file
                        #  into target metadata file.
                        s_meta = os.path.join(workdir,"s_meta")
                        with open(s_meta,"wb") as f:
                            _write_zipfile_metadata(f,s_zf)
                        t_meta = os.path.join(workdir,"t_meta")
                        with open(t_meta,"wb") as f:
                            _write_zipfile_metadata(f,t_zf)
                        self._diff_binary_file(s_meta,t_meta)
                        self._write_command(END)
                        #  Write commands to transform source contents
                        #  directory into target contents directory.
                        s_workdir = os.path.join(workdir,"source")
                        t_workdir = os.path.join(workdir,"target")
                        extract_zipfile(source,s_workdir)
                        extract_zipfile(target,t_workdir)
                        self._diff(s_workdir,t_workdir)
                        self._write_command(END)
                finally:
                    t_zf.close() 
                    s_zf.close() 


    def _diff_binary_file(self,source,target):
        """Diff a generic binary file.

        This is the per-file diffing method used when we don't know enough
        about the file to do anything fancier.  It's basically a windowed
        bsdiff.
        """
        spos = 0
        with open(target,"rb") as tfile:
            if os.path.isfile(source):
                sfile = open(source,"rb")
            else:
                sfile = None
            try:
                #  Process the file in diff_window_size blocks.  This
                #  will produce slightly bigger patches but we avoid
                #  running out of memory for large files.
                tdata = tfile.read(self.diff_window_size)
                if not tdata:
                    #  The file is empty, do a raw insert of zero bytes.
                    self._write_command(PF_INS_RAW)
                    self._write_bytes("".encode("ascii"))
                else:
                    while tdata:
                        sdata = ""
                        if sfile is not None:
                            sdata = sfile.read(self.diff_window_size)
                        #  Look for a shared prefix.
                        i = 0; maxi = min(len(tdata),len(sdata))
                        while i < maxi and tdata[i] == sdata[i]:
                            i += 1
                        #  Copy it in directly, unless it's tiny.
                        if i > 8:
                            skipbytes = sfile.tell() - len(sdata) - spos
                            if skipbytes > 0:
                                self._write_command(PF_SKIP)
                                self._write_int(skipbytes)
                                spos += skipbytes
                            self._write_command(PF_COPY)
                            self._write_int(i)
                            tdata = tdata[i:]; sdata = sdata[i:]
                            spos += i
                        #  Write the rest of the block as a diff
                        if tdata:
                            spos += self._write_file_patch(sdata,tdata)
                        tdata = tfile.read(self.diff_window_size)
            finally:
                if sfile is not None:
                    sfile.close()

    def _find_similar_sibling(self,source,target,nm):
        """Find a sibling of an entry against which we can calculate a diff.

        Given two directories 'source' and 'target' and an entry from the target
        directory 'nm', this function finds an entry from the source directory
        that we can diff against to produce 'nm'.

        The idea here is to detect files or directories that have been moved,
        and avoid generating huge patches by diffing against the original.
        We use some pretty simple heuristics but it can make a big difference.
        """
        t_nm = os.path.join(target,nm)
        if os.path.isfile(t_nm):
             # For files, I haven't decided on a good heuristic yet...
            return None
        elif os.path.isdir(t_nm):
            #  For directories, decide similarity based on the number of
            #  entry names they have in common.  This is very simple but should
            #  work well for the use cases we're facing in esky.
            if not os.path.isdir(source):
                return None
            t_names = set(os.listdir(t_nm))
            best = (2,None)
            for sibnm in os.listdir(source):
                if not os.path.isdir(os.path.join(source,sibnm)):
                    continue
                if os.path.exists(os.path.join(target,sibnm)):
                    continue
                sib_names = set(os.listdir(os.path.join(source,sibnm)))
                cur = (len(sib_names & t_names),sibnm)
                if cur > best:
                    best = cur
            return best[1]
        else:
            return None

    def _write_file_patch(self,sdata,tdata):
        """Write a series of PF_* commands to generate tdata from sdata.

        This function tries the various PF_* commands to find the one which can
        generate tdata from sdata with the smallest command size.  Usually that
        will be BSDIFF4, but you never know :-)
        """
        options = []
        #  We could just include the raw data
        options.append((0,PF_INS_RAW,tdata))
        #  We could bzip2 the raw data
        options.append((0,PF_INS_BZ2,bz2.compress(tdata)))
        #  We could bsdiff4 the data, if we have an appropriate module
        if bsdiff4.diff is not None:
            patch_data = bsdiff4.diff(sdata,tdata)
            # remove the 8 header bytes, we know it's BSDIFF4 format
            options.append((len(sdata),PF_BSDIFF4,len(sdata),patch_data[8:]))
        #  Find the option with the smallest data and use that.
        options = [(len(cmd[-1]),cmd) for cmd in options]
        options.sort()
        best_option = options[0][1]
        self._write_command(best_option[1])
        for arg in best_option[2:]:
            if isinstance(arg,(str,unicode,bytes)):
                self._write_bytes(arg)
            else:
                self._write_int(arg)
        return best_option[0]


class _tempdir(object):
    def __init__(self):
        self.path = tempfile.mkdtemp()
    def __enter__(self):
        return self.path
    def __exit__(self,*args):
        really_rmtree(self.path)





def _decode_offt(bytes):
    """Decode an off_t value from a string.

    This decodes a signed integer into 8 bytes.  I'd prefer some sort of
    signed vint representation, but this is the format used by bsdiff4.
    """
    if sys.version_info[0] < 3:
        bytes = map(ord,bytes)
    x = bytes[7] & 0x7F
    for b in xrange(6,-1,-1):
        x = x * 256 + bytes[b]
    if bytes[7] & 0x80:
        x = -x
    return x

def _encode_offt(x):
    """Encode an off_t value as a string.

    This encodes a signed integer into 8 bytes.  I'd prefer some sort of
    signed vint representation, but this is the format used by bsdiff4.
    """
    if x < 0:
        x = -x
        sign = 0x80
    else:
        sign = 0
    bs = [0]*8
    bs[0] = x % 256
    for b in xrange(7):
        x = (x - bs[b]) / 256
        bs[b+1] = x % 256
    bs[7] |= sign
    if sys.version_info[0] < 3:
        return "".join(map(chr,bs))
    else:
        return bytes(bs)



def main(args):
    """Command-line diffing and patching for esky."""
    parser = optparse.OptionParser()
    parser.add_option("-z","--zipped",action="store_true",dest="zipped",
                      help="work with zipped source/target dirs")
    parser.add_option("-Z","--deep-zipped",action="store_true",
                      dest="deep_zipped",
                      help="work with deep zipped source/target dirs")
    parser.add_option("","--diff-window",dest="diff_window",metavar="N",
                      help="set the window size for diffing files")
    parser.add_option("","--dry-run",dest="dry_run",action="store_true",
                      help="print commands instead of executing them")
    (opts,args) = parser.parse_args(args)
    if opts.deep_zipped:
        opts.zipped = True
    if opts.zipped:
        workdir = tempfile.mkdtemp()
    if opts.diff_window:
        scale = 1
        if opts.diff_window[-1].lower() == "k":
            scale = 1024
            opts.diff_window = opts.diff_window[:-1]
        elif opts.diff_window[-1].lower() == "m":
            scale = 1024 * 1024
            opts.diff_window = opts.diff_window[:-1]
        elif opts.diff_window[-1].lower() == "g":
            scale = 1024 * 1024 * 1024
            opts.diff_window = opts.diff_window[:-1]
        opts.diff_window = int(float(opts.diff_window)*scale)
    stream = None
    try:
        cmd = args[0]
        if cmd == "diff":
            #  Generate a diff between two files/directories.
            #  If --zipped is specified, the source and/or target is unzipped
            #  to a temporary directory before processing.
            source = args[1]
            target = args[2]
            if len(args) > 3:
                stream = open(args[3],"wb")
            else:
                stream = sys.stdout
            if opts.zipped:
                if os.path.isfile(source):
                    source_zip = source
                    source = os.path.join(workdir,"source")
                    if opts.deep_zipped:
                        deep_extract_zipfile(source_zip,source)
                    else:
                        extract_zipfile(source_zip,source)
                if os.path.isfile(target):
                    target_zip = target
                    target = os.path.join(workdir,"target")
                    if opts.deep_zipped:
                        deep_extract_zipfile(target_zip,target)
                    else:
                        extract_zipfile(target_zip,target)
            write_patch(source,target,stream,diff_window_size=opts.diff_window)
        elif cmd == "patch":
            #  Patch a file or directory.
            #  If --zipped is specified, the target is unzipped to a temporary
            #  directory before processing, then overwritten with a zipfile
            #  containing the new directory contents.
            target = args[1]
            if len(args) > 2:
                stream = open(args[2],"rb")
            else:
                stream = sys.stdin
            target_zip = None
            if opts.zipped:
                if os.path.isfile(target):
                    target_zip = target
                    target = os.path.join(workdir,"target")
                    if opts.deep_zipped:
                        deep_extract_zipfile(target_zip,target)
                    else:
                        extract_zipfile(target_zip,target)
            apply_patch(target,stream,dry_run=opts.dry_run)
            if opts.zipped and target_zip is not None:
                target_dir = os.path.dirname(target_zip)
                (fd,target_temp) = tempfile.mkstemp(dir=target_dir)
                os.close(fd)
                if opts.deep_zipped:
                    prefix = zipfile_common_prefix_dir(target_zip)
                    def name_filter(nm):
                        return prefix + nm
                    create_zipfile(target,target_temp,name_filter)
                else:
                    create_zipfile(target,target_temp)
                if sys.platform == "win32":
                    os.unlink(target_zip)
                    time.sleep(0.01)
                really_rename(target_temp,target_zip)
        else:
            raise ValueError("invalid command: " + cmd)
    finally:
        if stream is not None:
            if stream not in (sys.stdin,sys.stdout,):
                stream.close()
        if opts.zipped:
            really_rmtree(workdir)
 

if __name__ == "__main__":
    main(sys.argv[1:])


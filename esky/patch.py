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

      reach a patch from the file-like object "stream" and apply it to the
      directory (or file) at "tgtpath".  For directories, the patch is
      applied *in-situ*.  If you want to guard against patches that fail to
      apply, patch a copy then copy it back over the original.


This module can also be executed as a script (e.g. "python -m esky.patch ...")
to calculate or apply patches from the command-line:

  python -m esky.patch diff dir1 dir2 dir1_to_dir2.patch

      generate a patch to transform dir1 into dir2 and write it into the
      given filename (or stdout if not specified).

  python -m esky.patch patch dir1 dirs.patch

      transform dir1 by applying the patches in the given file (or stdin if
      not specified.  The modifications are made in-place.

To patch or diff zipfiles as though they were a directory, pass the "-z" or
"--zipped" option on the command-line, e.g:

  python -m esky.patch --zipped diff dir1.zip dir2.zip dir1_to_dir2.patch

This can be useful for generate differential esky updates by hand, when you
already have the corresponding zip files.

"""

from __future__ import with_statement

import os
import sys
import bz2
import shutil
import hashlib
import optparse
import zipfile
import tempfile
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

try:
    import bsdiff as cx_bsdiff
except ImportError:
    cx_bsdiff = None


#  Default size of blocks to use when diffing a file.  4M seems reasonable.
#  Setting this higher generates smaller patches at the cost of higher
#  memory use (and bsdiff is a memory hog at the best of times...)
DIFF_WINDOW_SIZE = 1024 * 1024 * 4

from esky.errors import Error
from esky.util import extract_zipfile, create_zipfile

__all__ = ["PatchError","DiffError","main","write_patch","apply_patch"]


class PatchError(Error):
    """Error raised when a patch fails to apply."""
    pass

class DiffError(Error):
    """Error raised when a diff can't be generated."""
    pass


#  Commands used in the directory patching protocol.  Each of these is
#  encoded as a vint in the patch stream; unless we get really out of
#  control that should mean one byte per command.
_COMMANDS = [
 "END",         # END():               stop processing at this point
 "SET_PATH",    # SET_PATH(path):      set current target path 
 "JOIN_PATH",   # JOIN_PATH(path):     join path to the current target
 "POP_PATH",    # POP_PATH(h):         pop one level off current target
 "VERIFY_MD5",  # VERIFY_MD5(dgst):    check md5 digest of current target
 "REMOVE",      # REMOVE():            remove the current target
 "MAKEDIR",     # MAKEDIR():           make directory at current target
 "COPY_FROM",   # COPY_FROM(path):     copy file/dir at path to current target
 "PF_COPY",     # PF_COPY(n):          patch file; copy n bytes from input
 "PF_SKIP",     # PF_SKIP(n):          patch file; skip n bytes from input
 "PF_INS_RAW",  # PF_INS_RAW(bytes):   patch file; insert raw bytes 
 "PF_INS_BZ2",  # PF_INS_BZ2(bytes):   patch file; insert unbzip'd bytes
 "PF_BSDIFF4",  # PF_BSDIFF4(n,ptch):  patch file; bsdiff4 from n input bytes
]

# Make commands available as global variables
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
    a directory, it is calculated from the names of digests of its contents.
    """
    d = hash()
    if os.path.isfile(target):
        with open(target,"rb") as f:
            data = f.read(1024*16)
            while data:
                d.update(data)
                data = f.read(1024*16)
    else:
        for nm in sorted(os.listdir(target)):
            d.update(nm)
            d.update(calculate_digest(os.path.join(target,nm)))
    return d.digest()


class Patcher(object):
    """Class interpreting our patch protocol.

    Instances of this class can be used to apply a sequence of patch commands
    to a target file or directory.  You can think of it as a little automaton
    that edits a directory in-situ.
    """

    def __init__(self,target,commands):
        target = os.path.abspath(target)
        self.target = target
        self.commands = commands
        self.root_dir = self.target
        self.infile = None
        self.outfile = None

    def __del__(self):
        if self.infile:
            self.infile.close()
        if self.outfile:
            self.outfile.close()

    def _check_begin_patch(self):
        """Begin patching the current file, if not already.

        This method is called by all file-patching commands; if there is
        no file open for patching then the current target is opened.
        """
        if not self.outfile:
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

    def _check_end_patch(self):
        """Finish patching the current file, if there is one.

        This method is called by all non-file-patching commands; if there is
        a file open for patching then it is closed and committed.
        """
        if self.outfile:
            self.infile.close()
            self.infile = None
            self.outfile.close()
            self.outfile = None
            if os.path.exists(self.target):
               os.unlink(self.target)
            os.rename(self.new_target,self.target)
            self.new_target = None

    def _check_path(self,path=None):
        """Check that we're not traversing outside the root."""
        if path is None:
            path = self.target
        if path != self.root_dir:
            if not path.startswith(self.root_dir + os.sep):
                raise PatchError("traversed outside root_dir")

    def patch(self):
        """Interpret and apply patch commands to the target.

        This is a simple command loop that dispatches to the _do_<CMD>
        methods defined below.
        """
        cmd = read_command(self.commands)
        while cmd != END:
            getattr(self,"_do_" + _COMMANDS[cmd])()
            cmd = read_command(self.commands)
        self._do_END()

    def _do_END(self):
        """Execute the END command.

        This simply commit any outstanding file patches.
        """
        self._check_end_patch()

    def _do_SET_PATH(self):
        """Execute the SET_PATH command.

        This reads a path from the command stream, and sets the current
        target path to that path.
        """
        self._check_end_patch()
        path = read_path(self.commands)
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
        path = read_path(self.commands)
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

    def _do_VERIFY_MD5(self):
        """Execute the VERIFY_MD5 command.

        This reads 16 bytes from the command stream, and compares them to
        the calculated digest for the current target path.  If they differ,
        a PatchError is raised.
        """
        self._check_end_patch()
        digest = calculate_digest(self.target,hashlib.md5)
        if digest != self.commands.read(16):
            raise PatchError("incorrect MD5 digest")

    def _do_MAKEDIR(self):
        """Execute the MAKEDIR command.

        This makes a directory at the current target path.  It automatically
        removes any existing entry at that path, as well as creating any
        intermediate directories.
        """
        self._check_end_patch()
        if os.path.exists(self.target) and not os.path.isdir(self.target):
            os.unlink(self.target)
        os.makedirs(self.target)

    def _do_REMOVE(self):
        """Execute the REMOVE command.

        This forcibly removes the file or directory at the current target path.
        """
        self._check_end_patch()
        if os.path.isdir(self.target):
            shutil.rmtree(self.target)
        elif os.path.exists(self.target):
            os.unlink(self.target)

    def _do_COPY_FROM(self):
        """Execute the COPY_FROM command.

        This reads a path from the command stream, and copies whatever is
        at that path to the current target path.  The source path is
        interpreted relative to the directory containing the current path;
        this caters for the common case of copy a file within the same
        directory.
        """
        self._check_end_patch()
        source_path = os.path.join(os.path.dirname(self.target),read_path(self.commands))
        self._check_path(source_path)
        if os.path.exists(self.target):
            if os.path.isdir(self.target):
                shutil.rmtree(self.target)
            else:
                os.unlink(self.target)
        if os.path.isfile(source_path):
            shutil.copy2(source_path,self.target)
        else:
            shutil.copytree(source_path,self.target)

    def _do_PF_COPY(self):
        """Execute the PF_COPY command.

        This generates new data for the file currently being patched.  It
        reads an integer from the command stream, then copies that many bytes
        directory from the source file into the target file.
        """
        self._check_begin_patch()
        n = read_vint(self.commands)
        self.outfile.write(self.infile.read(n))

    def _do_PF_SKIP(self):
        """Execute the PF_SKIP command.

        This reads an integer from the command stream, then moves the source
        file pointer by that amount without changing the target file.
        """
        self._check_begin_patch()
        n = read_vint(self.commands)
        self.infile.read(n)

    def _do_PF_INS_RAW(self):
        """Execute the PF_INS_RAW command.

        This generates new data for the file currently being patched.  It
        reads a bytestring from the command stream and writes it directly
        into the target file.
        """
        self._check_begin_patch()
        data = read_bytes(self.commands)
        self.outfile.write(data)

    def _do_PF_INS_BZ2(self):
        """Execute the PF_INS_BZ2 command.

        This generates new data for the file currently being patched.  It
        reads a bytestring from the command stream, decompresses it using
        bz2 and and write the result into the target file.
        """
        self._check_begin_patch()
        data = read_bytes(self.commands)
        self.outfile.write(bz2.decompress(data))

    def _do_PF_BSDIFF4(self):
        """Execute the PF_BSDIFF4 command.

        This reads an integer N and a BSDIFF4-format patch bytestring from
        the command stream.  It then reads N bytes from the source file,
        applies the patch to these bytes, and writes the result into the
        target file.
        """
        self._check_begin_patch()
        n = read_vint(self.commands)
        source = self.infile.read(n)
        # we must restore the 8 header bytes to the patch
        patch = "BSDIFF40" + read_bytes(self.commands)
        self.outfile.write(bsdiff4_patch(source,patch))


def apply_patch(target,stream):
    """Apply patch commands from the given stream to the given target.

    'target' must be the path of a file or directory, and 'stream' an object
    supporting the read() method.  Patch protocol commands will be read from
    the stream and applied in sequence to the target.
    """
    Patcher(target,stream).patch()


def write_patch(source,target,stream):
    """Generate patch commands to transform source into target.

    'source' and 'target' must be paths to a file or directory, and 'stream'
    an object supporting the write() method.  Patch protocol commands to
    transform 'source' into 'target' will be generated and written sequentially
    to the stream.
    """
    _write_patch(source,target,stream)
    write_command(stream,SET_PATH)
    write_bytes(stream,"")
    write_command(stream,VERIFY_MD5)
    stream.write(calculate_digest(target,hashlib.md5))
    write_command(stream,END)


def _write_patch(source,target,stream):
    """Recursively generate patch commands to transform source into target.

    This is the workhorse for the write_patch() function - it recursively
    generates the patch commands for a given (source,target) pair.  The
    main write_patch() function adds some header and footer commands.
    """
    #  If the target is a directory, generate commands to transform the
    #  source into a directory and then apply recursively.
    if os.path.isdir(target):
        if not os.path.isdir(source):
            write_command(stream,MAKEDIR)
        for nm in os.listdir(target):
            s_nm = os.path.join(source,nm)
            t_nm = os.path.join(target,nm)
            #  If this is a new file or directory, try to find a promising
            #  sibling against which to diff.  This might generate a few
            #  spurious COPY_FROM and REMOVE commands, but in return we
            #  get a better chance of diffing against something.
            at_path = False
            if not os.path.exists(s_nm):
                sibnm = _find_similar_sibling(source,target,nm)
                if sibnm is not None:
                    s_nm = os.path.join(source,sibnm)
                    at_path = True
                    write_command(stream,JOIN_PATH)
                    write_path(stream,nm)
                    write_command(stream,COPY_FROM)
                    write_path(stream,sibnm)
            #  Recursively diff against the selected source directory
            if paths_differ(s_nm,t_nm):
                if not at_path:
                    write_command(stream,JOIN_PATH)
                    write_path(stream,nm)
                    at_path = True
                _write_patch(s_nm,t_nm,stream)
            if at_path:
                write_command(stream,POP_PATH)
        #  Remove anything that's no longer in the target dir
        if os.path.isdir(source):
            for nm in os.listdir(source):
                if not os.path.exists(os.path.join(target,nm)):
                    write_command(stream,JOIN_PATH)
                    write_path(stream,nm)
                    write_command(stream,REMOVE)
                    write_command(stream,POP_PATH)
    #  If the target is a file, generate patch commands to produce it.
    elif os.path.isfile(target):
        if paths_differ(source,target):
            tfile = open(target,"rb")
            if os.path.isfile(source):
                sfile = open(source,"rb")
            else:
                sfile = None
            try:
                #  Process the file in DIFF_WINDOW_SIZE blocks.  This
                #  will produce slightly bigger patches but we avoid
                #  running out of memory for large files.
                tdata = tfile.read(DIFF_WINDOW_SIZE)
                while tdata:
                    sdata = ""
                    if sfile is not None:
                        sdata = sfile.read(DIFF_WINDOW_SIZE)
                    #  Look for a shared prefix.
                    i = 0; maxi = min(len(tdata),len(sdata))
                    while i < maxi and tdata[i] == sdata[i]:
                        i += 1
                    #  Copy it in directly, unless it's tiny.
                    if i > 8:
                        write_command(stream,PF_COPY)
                        write_vint(stream,i)
                        tdata = tdata[i:]; sdata = sdata[i:]
                    #  Write the rest of the block as a diff
                    if tdata:
                        _write_file_patch(sdata,tdata,stream)
                    tdata = tfile.read(DIFF_WINDOW_SIZE)
            finally:
                tfile.close()
                if sfile:
                    sfile.close()
    #  We can't deal with any other objects for the moment.
    #  Could evntually add support for e.g. symlinks.
    else:
        raise DiffError("unknown filesystem object: " + target)


def _find_similar_sibling(source,target,nm):
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
        # For files, I haven't decided on a god heuristic yet...
        return None
    elif os.path.isdir(t_nm):
        #  For directories, decide similarity based on the number of
        #  entry names they have in common.  This is very simple but should
        #  work well for the use cases we're facing in esky.
        t_names = set(os.listdir(t_nm))
        best = (0,None)
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


def _write_file_patch(sdata,tdata,stream):
    """Write a series of PF_* commands to generate tdata from sdata.

    This function tries the various PF_* commands to find one which can
    generate tdata from sdata with the smallest command size.  Usually that
    will be BSDIFF4, but you never know :-)
    """
    options = []
    #  We could just include the raw data
    options.append((PF_INS_RAW,tdata))
    #  We could bzip2 the raw data
    options.append((PF_INS_BZ2,bz2.compress(tdata)))
    #  We could bsdiff4 the data, if we have cx-bsdiff installed
    if cx_bsdiff is not None:
        # remove the 8 header bytes, we know it's BSDIFF4 format
        options.append((PF_BSDIFF4,len(sdata),bsdiff4_diff(sdata,tdata)[8:]))
    #  Find the option with the smallest data and use that.
    options = [(len(cmd[-1]),cmd) for cmd in options]
    options.sort()
    best_option = options[0][1]
    write_command(stream,best_option[0])
    for arg in best_option[1:]:
        if isinstance(arg,basestring):
            write_bytes(stream,arg)
        else:
            write_vint(stream,arg)


if cx_bsdiff is not None:
    def bsdiff4_diff(source,target):
        """Generate a BSDIFF4-format patch from 'source' to 'target'.

        You must have cx-bsdiff installed for this to work; if I get really
        bored I might do a pure-python version but it would probably be too
        slow and ugly to be worthwhile.
        """
        (tcontrol,bdiff,bextra) = cx_bsdiff.Diff(source,target)
        #  Write control tuples as series of offts
        bcontrol = StringIO()
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
        #  (head)(len bcontrol)(len bdiff)(len target)(bcontrol)(bdiff)(bextra)
        return "".join((
            "BSDIFF40",
            _encode_offt(len(bcontrol)),
            _encode_offt(len(bdiff)),
            _encode_offt(len(target)),
            bcontrol,
            bdiff,
            bextra,
        ))


def bsdiff4_patch(source,patch):
    """Apply a BSDIFF4-format patch to the given string.

    This function returns the result of applying the BSDIFF4-format patch
    'patch' to the input string 'source'.  If cx-bsdiff is installed then
    it will be used; otherwise a pure-python fallback is used.

    The idea of a pure-python fallback is to avoid making frozen apps depend
    on cx-bsdiff; only the developer needs to have it installed.
    """
    #  Read the length headers
    l_bcontrol = _decode_offt(patch[8:16])
    l_bdiff = _decode_offt(patch[16:24])
    l_target = _decode_offt(patch[24:32])
    #  Read the three data blocks
    bcontrol = bz2.decompress(patch[32:32+l_bcontrol])
    bdiff = bz2.decompress(patch[32+l_bcontrol:32+l_bcontrol+l_bdiff])
    bextra = bz2.decompress(patch[32+l_bcontrol+l_bdiff:])
    #  Decode the control tuples 
    tcontrol = []
    for i in xrange(0,len(bcontrol),24):
        tcontrol.append((
            _decode_offt(bcontrol[i:i+8]),
            _decode_offt(bcontrol[i+8:i+16]),
            _decode_offt(bcontrol[i+16:i+24]),
        ))
    #  Actually do the patching.
    #  This is simple enough that I can provide a pure-python fallback
    #  when cx_bsdiff is not available.
    if cx_bsdiff is not None:
        return cx_bsdiff.Patch(source,l_target,tcontrol,bdiff,bextra)
    else:
        source = StringIO(source)
        result = StringIO()
        bdiff = StringIO(bdiff)
        bextra = StringIO(bextra)
        for (x,y,z) in tcontrol:
            diff_data = bdiff.read(x)
            orig_data = source.read(x)
            for i in xrange(len(diff_data)):
                result.write(chr((ord(diff_data[i])+ord(orig_data[i]))%256))
            result.write(bextra.read(y))
            source.seek(z,os.SEEK_CUR)
        return result.getvalue()


def _decode_offt(bytes):
    """Decode an off_t value from a string.

    This decodes a signed integer into 8 bytes.  I'd prefer some sort of
    signed vint representation, but it's the format used by bsdiff4....
    """
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
    signed vint representation, but it's the format used by bsdiff4....
    """
    if x < 0:
        x = -x
        sign = 0x80
    else:
        sign = 0
    bytes = [0]*8
    bytes[0] = x % 256
    for b in xrange(7):
        x = (x - bytes[b]) / 256
        bytes[b+1] = x % 256
    bytes[7] |= sign
    return "".join(map(chr,bytes))



def main(args):
    """Command-line diffing and patching for esky."""
    parser = optparse.OptionParser()
    parser.add_option("-z","--zipped",action="store_true",dest="zipped",
                      help="work with zipped source/target dirs")
    parser.add_option("","--diff-window",dest="diff_window",metavar="N",
                      help="set the window size for diffing files")
    (opts,args) = parser.parse_args(args)
    if opts.zipped:
        workdir = tempfile.mkdtemp()
    if opts.diff_window:
        global DIFF_WINDOW_SIZE
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
        DIFF_WINDOW_SIZE = opts.diff_window
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
                    extract_zipfile(source_zip,source)
                if os.path.isfile(target):
                    target_zip = target
                    target = os.path.join(workdir,"target")
                    extract_zipfile(target_zip,target)
            write_patch(source,target,stream)
        elif cmd == "patch":
            #  Patch a file or directory.
            #  If --zipped is specified, thetarget is unzipped to a temporary
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
                    extract_zipfile(target_zip,target)
            apply_patch(target,stream)
            if opts.zipped and target_zip is not None:
                target_dir = os.path.dirname(target_zip)
                (fd,target_temp) = tempfile.mkstemp(dir=target_dir)
                os.close(fd)
                create_zipfile(target,target_temp)
                if sys.platform == "win32":
                    os.unlink(target_zip)
                os.rename(target_temp,target_zip)
        else:
            raise ValueError("invalid command: " + cmd)
    finally:
        if opts.zipped:
            shutil.rmtree(workdir)
 

if __name__ == "__main__":
    main(sys.argv[1:])


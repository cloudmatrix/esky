"""

  esky.helper.__main__:  main application loop for esky update helper.

"""

import sys
import base64

from esky.helper import SubprocPipe

try:
    import cPickle as pickle
except ImportError:
    import pickle


_ALLOWED_METHODS = {
  "close": [],
  "has_root": [],
  "cleanup": [],
  "fetch_version": [str],
  "install_version": [str],
  "uninstall_version": [str]
}


if __name__ == "__main__":
    pipe = SubprocPipe(None,pickle.loads(base64.b64decode(sys.argv[1])))
    try:
        esky = pickle.loads(base64.b64decode(sys.argv[2]))
        pipe.write("READY")
        while True:
            try:
                method = pipe.read()
                try:
                    argspec = _ALLOWED_METHODS[method]
                except KeyError:
                    sys.exit(2)
                else:
                    if method == "close":
                        pipe.write("CLOSING")
                        break
                    args = [c(pipe.read()) for c in argspec]
                    try:
                        res = getattr(esky,method)(*args)
                    except Exception, e:
                        pipe.write(pickle.dumps((False,e)))
                    else:
                        pipe.write(pickle.dumps((True,res)))
            except EOFError:
                break
    finally:
        pipe.close()
    sys.exit(0)



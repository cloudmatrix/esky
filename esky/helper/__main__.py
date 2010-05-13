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


if __name__ == "__main__":
    pipe = SubprocPipe(None,pickle.loads(base64.b64decode(sys.argv[1])))
    try:
        esky = pipe.read()
        pipe.write("READY")
        while True:
            try:
                (method,args,kwds) = pipe.read()
                if method == "close":
                    pipe.write("CLOSING")
                else:
                    try:
                        res = getattr(esky,method)(*args,**kwds)
                    except Exception, e:
                        pipe.write((False,e))
                    else:
                        pipe.write((True,res))
            except EOFError:
                break
    finally:
        pipe.close()
    sys.exit(0)



from __future__ import print_function

import sys
import esky

if getattr(sys,"frozen",False):
    #app = esky.Esky(sys.executable,"https://example-app.com/downloads/")
    app = esky.Esky(sys.executable,"http://localhost:8000")
    try:
        app.auto_update()
    except Exception as e:
        print ("ERROR UPDATING APP:", e)

print("HELLO AGAAIN WORLD - Stage 2")


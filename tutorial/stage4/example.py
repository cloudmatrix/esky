
import sys
import esky

if getattr(sys,"frozen",False):
    app = esky.Esky(sys.executable,"https://example-app.com/downloads/")
    try:
        app.auto_update()
    except Exception, e:
        print "ERROR UPDATING APP:", e
    app.cleanup()

print "HELLO WORLD"


import sys
import os
import esky

if getattr(sys,"frozen",False):
    app = esky.Esky(sys.executable,"https://example-app.com/downloads/")
    print "You are running: %s" % app.active_version
    try:
        if(app.find_update() != None):
            app.auto_update()
            appexe = esky.util.appexe_from_executable(sys.executable)
            os.execv(appexe,[appexe] + sys.argv[1:])
    except Exception, e:
        print "ERROR UPDATING APP:", e
    app.cleanup()

print "HELLO WORLD"


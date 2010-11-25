
This directory contains a brief tutorial on using esky in your frozen 
applications.  It assumes some basic familiarity with distutils and
and a freezer module such as py2exe.

The sub-directories "stage0" through "stage4" contain example code showing
the evolution of a simple example app.  To run them you'll need to be on a
Windows machine with py2exe installed.


Step 1:  Freezing with Esky
===========================

In order to use the functionality of esky in your application, it must be
frozen using a certain file layout and directory structure.  The easiest way
to achieve this is to use the "bdist_esky" distutils command as a wrapper
around your freezer module of choice.

Consider the example application in the "stage0" directory.  This is a simple
application designed to be frozen with py2exe.  Run "python setup.py py2exe"
in this directory and you will see that the "dist" folder is created with
the frozen application directly inside it.

Now consider the modified application in the "stage1" directory.  Here we
have changed the setup.py script to use esky instead of directly calling py2exe.
Run "python setup.py bdist_esky" in this directory - esky will automatically
detect that you have py2exe installed and use that to freeze the application.

The "dist" directory will now contain a file named "example-app-0.1.win32.zip".
This zipfile contains a specific version of the application frozen in the 
format expected by esky.  If you unzip it, you will see the application is laid
out according to the following structure:

    example.exe              <-- bootstrapping exe produced by esky
    appdata/
      example-app-0.1.win32/   <-- directory containing the frozen application
        example.exe              as produced by py2exe
        library.zip
        python26.dll
        esky-files/
          bootstrap-manifest.txt   <-- extra metadata for use during updates
        
The top-level "example.exe" is a bootstrapping executable produced by esky.
The "example-app-0.1.win32" directory contains the application exactly as
frozen by py2exe, but with some extra files containing metadata for use when
updating the app.

You can distribute these files to your users in any manner - e.g. by having
them download and extract the zipfile directly, or by packaging it up into
an installer.  As long as the above file layout and directory structure is
maintained, the application will be capable of auto-updating itself with esky.


Step 2:  Looking For Updates
============================

Next, we must add code to our application to make it search for, download
and installed updated versions of itself.  The interface for doing so is
the "Esky" class, which represents a container for your frozen application.
We create one like so:

    app = esky.Esky(sys.executable,"http://example-app.com/downloads/")

The Esky must be given its location on disk, and a url at which to look for
updated versions. Instances of Esky then have the following useful methods:

    find_update():         check for updated versions of the app
    fetch_version():       download a specific version of the app
    install_version():     install a specific version of the app   
    uninstall_version():   uninstall a specific version of the app 
    cleanup():             remove any old versions, partial downloads etc.

For convenience, it also has this method:

    auto_update():   check for an updated version; install it if found

Looking at the code in stage2/example.py, we can see that the application now
checks whether it is running as a frozen app, and if so it:

    * creates an Esky pointing at an appropriate URL, and
    * calls the "auto_update" method on the esky to search for and install
      a new version of the app.

A real application would probably want to perform these tasks in a background
thread, prompt the user for confirmation, and so-on.  Nonetheless, our simple
example application is now capable of auto-updating itself over the internet.



Step 3:  Distributing Updates
=============================

You've already seen how this step works.  Whenever a new version of the 
application is released, run the "bdist_esky" command and make the resulting
zipfile available for download from the update URL specified in your code.
The app will automatically detect the update, download and install it.

One point of watch out for: you must not change the name of the zipfile
produced by bdist_esky.  Since it embeds version and platform information,
changing the name could cause esky to get confused about which version really
is the latest.

Esky also supports distributing your updates as a patch instead of (or as well
as) a full zipfile download.  To see this in action, copy the "dist" folder
you built in stage 2 into the "stage3" folder.  You should have the following
files:

    stage3/example.py
    stage3/setup.py
    stage3/dist/example-0.2.win32.zip

Now run "python setup.py bdist_esky_patch" in the stage3 directory.  This will
generate the zipfile for the new version along with a patch against any other
zipfiles found in the "dist" dir.  You should now have:

    stage3/dist/example-0.2.win32.zip
    stage3/dist/example-0.3.win32.zip
    stage3/dist/example-0.3.win32.from-0.2.patch

As before, simply make this patch file available for download from your update
URL and esky will detect and use it as appropriate.

It's also possible to generate patches between two existing zipfiles, without
going through the setup.py script.  Simply invoke the "esky.patch" module
directly as follows:

    python -m esky.patch -Z diff ../stage1/dist/example-0.1.win32.zip ./dist/example-0.2.win32.zip ./dist/example-0.2.win32.from-0.1.patch

Don't forget the "-Z" argument - it tells the patcher to unzip the source files
before starting work.  You should now have:

    stage3/dist/example-0.2.win32.zip
    stage3/dist/example-0.2.win32.from-0.1.patch
    stage3/dist/example-0.3.win32.zip
    stage3/dist/example-0.3.win32.from-0.2.patch

By the way, esky is smart enough to apply a sequence of patches to get to the
latest version, so there's no need to also generate a patch from version 0.1
to 0.3 in this case.


Step 4:  Customising the Freeze Process
=======================================

Most users will not need to customise the freeze procees performed by the
bdist_esky command - it automatically detects any available freezer modules
(e.g. py2exe, cx_Freeze, bbfreeze) and applies some sensible defaults for you.
If necessary, however, you can pass options either on the setup.py command line,
or using the "options" argument to the setup() function.

The code in the "stage4" directory shows an example of how to customise the
freeze process.  Here we specify a custom icon for the executable, list some
modules to explicitly include and exclude from the freeze, and give additional
options that are passed through to py2exe.



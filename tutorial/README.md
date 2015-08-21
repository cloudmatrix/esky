
Esky Tutorial
=============

This directory contains a brief tutorial on using esky in your frozen 
applications. You will need a freezer module installed.

This guide will focus on telling you what to do and to get your feet wet,
jump into the source code of the examples for the details.

## Choosing a Freezer

Esky currently supports
 - cx_freeze
 - py2exe 
 - py2app 
 - bbfreeze (we will be removing support next release as this is no longer maintained)

We suggest that you use **cx_freeze** because it is/supports:
 - python2
 - python3
 - maintained 
 - linux
 - mac 
 - windows

### Tutorial Stage0 - Freezing an app

Its probably better to read the official documentation for your freezer but
here is what you need to freeze the code in the stage0 folder:

**cxfreeze** `setup.py build`

**py2app** `python setup.py py2app`

**py2exe** `python setup.py py2exe`

**bbfreeze** `bdist_bbfreeze`

## Step 1:  Freezing with Esky 

We now set up the machinery for esky to work. Here we have changed the setup.py 
script to use esky instead of directly calling our freezer. You will need 
to edit and uncomment the block of code depending on your freezer.

`python setup.py bdist_esky`

The "dist" directory will now contain a file named "example-app-0.1.win32.zip".

Now unzip and run example.exe
        
The top-level "example.exe" is a bootstrapping executable produced by esky.
The bootstrapping file is the one that needs to open for updating to
work.


## Step 2:  Looking For Updates

Next, we must add code to our application to make it update. 
The interface for doing so is the "Esky" class, which represents 
a container for your frozen application.
We create one like so:

    app = esky.Esky(sys.executable,"http://localhost:8000")

The Esky must be given its location on disk, and a url at which to look for
updated versions. 

`cd stage2`

`python setup.py bdist_esky`

again unzip

Start up a little http server by running the following command

`python2 -m SimpleHTTPServer 8000`

or for python3

`python -m http.server 8000`

When you execute example.exe you will see a GET reponse on the server.


## Step 3:  Distributing Updates

Ok lets make something to update!

 - `cd stage3`

 - `python setup.py bdist_esky`

The python webserver will serve the folder from whose current working
directory we started it in so navigate to "stage3/dist/" and start the server.
Lets go ahead and see if we can update stage2/dist/example.exe.


After running the exe you will now see a GET request followed shortly by
a second one for fetching the new update.

Now run "stage2/dist/example.exe"

Notice the new print message!

### Patches

Esky supports distributing your updates as a patch instead of (or as well
as) a full zipfile download. To see this in action:

 - delete all the files from "stage2/dist/" besides the example-0.2.zip

 - unzip

Our app is back to version 2. 

 - Copy the dist folder you built in stage 2 into the "stage3" folder. 

You should have the following files:

    stage3/example.py
    stage3/setup.py
    stage3/dist/example-0.2.win32.zip

 - `cd stage3`
 - `python setup.py bdist_esky_patch` 

This will generate the zipfile for the new version along with a patch against any other
zipfiles found in the "dist" dir.  You should now have:

    stage3/dist/example-0.2.win32.zip
    stage3/dist/example-0.3.win32.zip
    stage3/dist/example-0.3.win32.from-0.2.patch

You can follow the same procedure as before to test that the app update via
our patch.

### More on Patching 

It's also possible to generate patches between two existing zipfiles, without
going through the setup.py script.  Simply invoke the "esky.patch" module
directly as follows:

'python -m esky.patch -Z diff ../stage1/dist/example-0.1.win32.zip ./dist/example-0.2.win32.zip ./dist/example-0.2.win32.from-0.1.patch`

Don't forget the "-Z" argument - it tells the patcher to unzip the source files
before starting work.  You should now have:

    stage3/dist/example-0.2.win32.zip
    stage3/dist/example-0.2.win32.from-0.1.patch
    stage3/dist/example-0.3.win32.zip
    stage3/dist/example-0.3.win32.from-0.2.patch

By the way, esky is smart enough to apply a sequence of patches to get to the
latest version, so there's no need to also generate a patch from version 0.1
to 0.3 in this case.

### Distributing 

You can distribute these files to your users in any manner - e.g. by having
them download and extract the zipfile directly, or by packaging it up into
an installer.  As long as the above file layout and directory structure is
maintained, the application will be capable of auto-updating itself with esky.

One point of watch out for: you must not change the name of the zipfile
produced by bdist_esky.  Since it embeds version and platform information,
changing the name could cause esky to get confused about which version really
is the latest.


## Step 4: Customizing the Freeze Process

Most users will not need to customize the freeze procees performed by the
bdist_esky command - it automatically detects any available freezer modules
(e.g. py2exe, cx_Freeze, bbfreeze) and applies some sensible defaults for you.
If necessary, however, you can pass options either on the setup.py command line,
or using the "options" argument to the setup() function.

The code in the "stage4" directory shows an example of how to customize the
freeze process.  Here we specify a custom icon for the executable, list some
modules to explicitly include and exclude from the freeze, and give additional
options that are passed through to py2exe.

**Unfortunately the example is with py2exe which is having problems at the
moment!**

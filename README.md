
Status: Unmaintained
====================

[![No Maintenance Intended](http://unmaintained.tech/badge.svg)](http://unmaintained.tech/)

This project is [no longer actively maintained](https://rfk.id.au/blog/entry/archiving-open-source-projects/).

Thanks to @timeyyy for helping to push it along for a while!


News
====

 Esky, is again unmaintained.
 I would reccomend trying `pyinstaller` and `pyupdater`
 It seems to be the king.

 There are some useful modules here such as the functions to get admin access. These
 could be made reusable for other projects.

 I would also like to encourage people to collaborate instead of always spin
 off new libraries. Why do we have 4 actively maintained freezers for python????


Esky  - keep frozen apps fresh
==============================

[![Join the chat at https://gitter.im/cloudmatrix/esky](https://badges.gitter.im/Join%20Chat.svg)](https://gitter.im/cloudmatrix/esky?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)
[![Build Status](https://travis-ci.org/cloudmatrix/esky.svg)](https://travis-ci.org/cloudmatrix/esky)
[![Build status](https://ci.appveyor.com/api/projects/status/qsl966pqssff9lpt?svg=true&pendingText=Windows%20Pending&failingText=Windows%20Failing&passingText=Windows%20Passing)](https://ci.appveyor.com/project/tim83455/esky-r8uvn)
[![Code Climate](https://codeclimate.com/github/cloudmatrix/esky/badges/gpa.svg)](https://codeclimate.com/github/cloudmatrix/esky)

Esky is an auto-update framework for frozen Python applications.  It provides
a simple API through which apps can find, fetch and install updates, and a
bootstrapping mechanism that keeps the app safe in the face of failed or
partial updates. Updates can also be sent as differential patches.

Esky is currently capable of freezing apps with py2exe, py2app, cxfreeze and
bbfreeze. Adding support for other freezer programs should be easy;
patches will be gratefully accepted.

We are tested and running on Python 2.7
Py2app will work on python3 fine, the other freezers not so much.

#### Current Limitations
 - Cannot sign the bootstrap executable
 - Doesn't work with windows resources
 - cxfreeze and py2exe not working on python3
 - Only support cxfreeze 4

For some workarounds to common issues check out the wiki


Installation
------------

The simplest way to install esky is

`pip install esky`

To install the latest development branch you can install directly from github with

`git clone git@github.com:cloudmatrix/esky.git`

`pip install -e esky`

**To uninstall the development version do** `python setup.py develop --uninstall`


Usage
-----

Freezing your app with esky requires small some modification to a setup.py file and then adding the Esky class to your program.
When you are ready just run `python setup.py bdist_esky`
This will produce a zip file which can automatically update as long as the structure is kept in tact.

- The [tutorial](https://github.com/cloudmatrix/esky/tree/master/tutorial) will guide you through setting up and freezing with esky. (get the files by cloning)

- We have an F.A.Q as well as Documentation in our [wiki](https://github.com/cloudmatrix/esky/wiki)

- Ryan has done a talk at Pycon to help you get started: [Keep your frozen app fresh](http://pyvideo.org/video/470/pyconau-2010--esky--keep-your-frozen-apps-fresh)

- There is also a wrapper for esky in the gui library wxpthon, see [blog post](http://www.blog.pythonlibrary.org/2013/07/12/wxpython-updating-your-application-with-esky/) 


Features
--------

- Pull updates from a http server or amazon s3 bucket (easily extendable)

- Bootstrap Executable to prevent corruption in failed updates (can be compiled to ~1mb using Rpython)

- Differential Patching (minor updates and fixes can be < 10kb)

- py2exe, py2app, cxfreeze


Getting in Contact
------------------

* Questions about usage can be posted on stackoverflow.
* Bugs and problems can be posted at our github issue tracker.
* Chats and so on can be done through gitter.


Development / Contributing
--------------------------

We welcome all contributors.
See the [Contributing Guide](https://github.com/cloudmatrix/esky/wiki/Contributing)

#### Author

[Ryan Kelly](https://github.com/rfk)

#### Current Core

 - No one

#### Contributors

[Thanks all Contributors](https://github.com/cloudmatrix/esky/graphs/contributors)

The above list isn't complete, some people seem to be missing or contribute in other ways.

* JPFrancoia

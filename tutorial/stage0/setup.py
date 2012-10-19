import sys
# for windows
# > python setup.py py2exe
if sys.platform == 'win32' or sys.platform == 'cygwin':
    import py2exe
    from distutils.core import setup

    setup(
        name = "example-app",
        version = "0.0",
        console = ["example.py"]
    )

# for mac
# > python setup.py py2app
elif sys.platform == 'darwin':
    from setuptools import setup
    
    setup(
        name = "example-app",
        app=["example.py"],
        version = "0.0",
        setup_requires=["py2app"],
        options={'py2app':{}},
    )
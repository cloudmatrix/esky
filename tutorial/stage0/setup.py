import sys
# for windows
# > python setup.py py2exe
if sys.argv[1] == 'py2exe':    
    import py2exe
    from distutils.core import setup
    setup(
        name = "example-app",
        version = "0.0",
        console = ["example.py"]
    )

# for mac
# > python setup.py py2app
elif sys.argv[1] == 'py2app':
    from setuptools import setup
    
    setup(
        name = "example-app",
        app=["example.py"],
        version = "0.0",
        setup_requires=["py2app"],
        options={'py2app':{}},
    )

# cx freeze cross platform
# > python setup.py build
elif sys.argv[1] == 'build':
    from cx_Freeze import setup, Executable
    setup(
        name = 'example-app',
	version = '0.0',
	executables=[Executable('example.py')],
    )
   

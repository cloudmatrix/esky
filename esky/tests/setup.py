
from distutils.core import setup
from esky import bdist_esky

setup(name="mypkg",
      packages=["mypkg"],
      scripts=["mypkg/runme.py"],
      version="0.0.0",
      author="Ryan Kelly",
      author_email="ryan@rfk.id.au",
      description="a test package",
      license="GPL",
     )


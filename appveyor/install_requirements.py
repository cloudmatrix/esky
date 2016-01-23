from __future__ import print_function
import sys
import os
import subprocess as sub


is_py2 = sys.version_info[0] < 3;


if is_py2:
	file = 'appveyor-requirements-py2.txt'
else:
	file = 'appveyor-requirements.txt'


proc = sub.Popen('pip install -r '+file,
		stderr=sub.PIPE,
		stdout=sub.PIPE,
        cwd=os.path.join(os.getcwd(),'appveyor'))
out, errs = proc.communicate()

if out:
	print(out)
if errs:
	print(errs)
